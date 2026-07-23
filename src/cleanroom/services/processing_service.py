import asyncio
import hashlib
import logging
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from cleanroom.config.settings import Settings
from cleanroom.database.models import JobRecord
from cleanroom.database.repository import JobRepository
from cleanroom.detectors.merge import merge_findings
from cleanroom.detectors.regex_detector import RegexDetector
from cleanroom.files.lifecycle import atomic_write_text, move_generated, move_original
from cleanroom.files.manifest import JobManifest
from cleanroom.files.pdf_handler import PdfDocumentHandler, PdfError, PdfUnsupportedError
from cleanroom.files.registry import DocumentHandlerRegistry
from cleanroom.files.text_handler import TextDocumentHandler, file_hash, validate_input, wait_until_stable
from cleanroom.files.workspace_lock import WorkspaceLock
from cleanroom.logging import safe_diagnostic
from cleanroom.models.job import JobCreate, JobStatus, utcnow
from cleanroom.models.pdf import PdfExtractedDocument, PdfInspection
from cleanroom.models.policy import Action, SanitizationPolicy
from cleanroom.models.report import AuditReport, VerificationReport
from cleanroom.providers.base import DetectionProvider
from cleanroom.sanitizers.text_sanitizer import sanitize_text
from cleanroom.services.chunking import ChunkedDetector
from cleanroom.services.report_service import ReportService, source_counts
from cleanroom.services.verification_service import VerificationService

LOG = logging.getLogger(__name__)


class DuplicateFileError(ValueError):
    pass


class ProcessingService:
    def __init__(self, settings: Settings, policy: SanitizationPolicy, repository: JobRepository,
                 provider: DetectionProvider, regex: RegexDetector | None = None,
                 handlers: DocumentHandlerRegistry | None = None) -> None:
        self.settings, self.policy, self.repository, self.provider = settings, policy, repository, provider
        self.regex = regex or RegexDetector()
        self.chunker = ChunkedDetector(provider, settings.chunk_max_chars,
                                       settings.chunk_overlap_chars, settings.max_chunks_per_file)
        self.verifier = VerificationService(self.regex, provider, self.chunker)
        self.reports = ReportService(settings.reports_dir, settings.write_review_diff)
        self.handlers = handlers or DocumentHandlerRegistry([
            TextDocumentHandler(policy), PdfDocumentHandler(policy, settings)])
        self._lock = asyncio.Lock()

    async def process(self, input_path: Path, check_stability: bool = True,
                      stage_callback: Callable[[str], None] | None = None) -> JobRecord:
        workspace_lock = WorkspaceLock(self.settings.temp_dir.parent / "workspace.lock")
        with workspace_lock:
            return await self._process_locked(input_path, check_stability, stage_callback)

    async def _process_locked(self, input_path: Path, check_stability: bool,
                              stage_callback: Callable[[str], None] | None) -> JobRecord:
        async with self._lock:
            path = validate_input(input_path, self.settings.dirty_dir,
                                  self.settings.max_file_size_mb * 1024 * 1024,
                                  self.settings.extension_set)
            if check_stability:
                await wait_until_stable(path, self.settings.file_stability_seconds)
            digest = file_hash(path)
            prior = self.repository.find_by_hash(digest)
            if prior and prior.status not in {
                JobStatus.FAILED.value, JobStatus.INTERRUPTED.value
            }:
                raise DuplicateFileError("this file hash already has a job")
            job = self.repository.create(JobCreate(source_filename=path.name, source_path=str(path),
                source_hash=digest, model=self.settings.ollama_model, policy_name=self.policy.name,
                policy_version=self.policy.version))
            started = utcnow()
            manifest = JobManifest(self.settings.temp_dir, job.id, path.name)
            manifest.update("pending")
            handler = self.handlers.for_path(path)
            if isinstance(handler, PdfDocumentHandler):
                return await self._process_pdf(path, digest, job, started, manifest,
                                               handler, stage_callback)
            try:
                self.repository.update(job.id, JobStatus.PROCESSING)
                manifest.update("reading")
                self._stage(stage_callback, "Reading")
                text = handler.extract(path).text
                self.repository.update(job.id, JobStatus.ANALYZING)
                manifest.update("detecting")
                self._stage(stage_callback, "Detecting")
                deterministic = await self.regex.detect(text, self.policy)
                chunked = await self.chunker.detect(text, self.policy, deterministic)
                merged = merge_findings(text, deterministic + chunked.findings)
                accepted = [f for f in merged.findings
                            if f.confidence >= self.policy.threshold_for(f.category)]
                self.repository.update(job.id, JobStatus.SANITIZING, findings_count=len(accepted))
                manifest.update("sanitizing")
                self._stage(stage_callback, "Sanitizing")
                sanitized = sanitize_text(text, accepted, self.policy)
                self.repository.update(job.id, JobStatus.VERIFYING)
                manifest.update("verifying")
                self._stage(stage_callback, "Verifying")
                replaced_findings = [
                    finding for finding in accepted
                    if self.policy.actions[finding.category] in {Action.REPLACE, Action.REDACT}
                    or (self.policy.actions[finding.category] == Action.REVIEW
                        and self.policy.review_behavior.auto_replace)
                ]
                review_findings = [finding for finding in accepted
                                   if self.policy.actions[finding.category] == Action.REVIEW]
                allowed_review_values = ({finding.text for finding in review_findings}
                    if self.policy.review_behavior.warn_only else None)
                verification = (await self.verifier.verify(sanitized.text, replaced_findings,
                    self.policy, self.settings.ollama_verify, allowed_review_values)
                    if self.settings.verify_output else
                    VerificationReport(passed=True, remaining_findings_count=0))
                output_name = f"{path.stem}-clean.txt"
                review_quarantine = (bool(review_findings)
                    and self.policy.review_behavior.quarantine
                    and not self.policy.review_behavior.auto_replace)
                clean_result = verification.passed and not review_quarantine
                target = self.settings.spotless_dir if clean_result else self.settings.quarantine_dir
                manifest.update("writing")
                self._stage(stage_callback, "Writing output")
                output_path = atomic_write_text(target, output_name, sanitized.text)
                moved = (move_original(path, self.settings.processed_dir)
                         if self.settings.archive_processed else path)
                status = JobStatus.COMPLETED if clean_result else JobStatus.QUARANTINED
                completed = utcnow()
                report = AuditReport(job_id=job.id, source_filename=path.name, source_hash=digest,
                    output_filename=output_path.name, status=status, started_at=started,
                    completed_at=completed, model=self.settings.ollama_model,
                    policy={"name": self.policy.name, "version": self.policy.version},
                    findings_count=len(accepted), findings_by_category=dict(Counter(f.category for f in accepted)),
                    findings_by_source=source_counts(accepted),
                    review_findings=[{"category": finding.category.value,
                        "original_hash": hashlib.sha256(finding.text.encode()).hexdigest(),
                        "confidence": finding.confidence} for finding in review_findings],
                    chunk_telemetry={
                        "chunk_count": chunked.telemetry.chunk_count,
                        "average_chunk_duration": chunked.telemetry.average_chunk_duration,
                        "total_inference_duration": chunked.telemetry.total_inference_duration,
                        "retry_count": chunked.telemetry.retry_count,
                        "invalid_finding_count": chunked.telemetry.invalid_finding_count,
                    },
                    replacements=sanitized.replacements, ambiguous_overlaps=merged.ambiguous,
                    verification=verification)
                report_path, _ = self.reports.write(path.stem, report, text, sanitized.text)
                result = self.repository.update(job.id, status, output_path=str(output_path),
                    source_path=str(moved), report_path=str(report_path),
                    verification_result=verification.passed, findings_count=len(accepted))
                manifest.close()
                return result

            except Exception as exc:
                LOG.error("job=%s file=%s failed code=%s", job.id, path.name, type(exc).__name__)
                failed_path = move_original(path, self.settings.failed_dir) if path.exists() else path
                report = AuditReport(job_id=job.id, source_filename=path.name, source_hash=digest,
                    output_filename=None, status=JobStatus.FAILED, started_at=started, completed_at=utcnow(),
                    model=self.settings.ollama_model, policy={"name": self.policy.name,
                    "version": self.policy.version}, findings_count=0, findings_by_category={},
                    replacements=[], verification=VerificationReport(passed=False,
                    remaining_findings_count=0), error={"code": type(exc).__name__,
                    "message": safe_diagnostic(exc)})
                report_path, _ = self.reports.write(f"{path.stem}-error", report)
                result = self.repository.update(job.id, JobStatus.FAILED, source_path=str(failed_path),
                    report_path=str(report_path), verification_result=False,
                    error_code=type(exc).__name__, error_message=safe_diagnostic(exc))
                manifest.close()
                return result

    async def _process_pdf(self, path: Path, digest: str, job: JobRecord,
                           started: datetime, manifest: JobManifest,
                           handler: PdfDocumentHandler,
                           stage_callback: Callable[[str], None] | None) -> JobRecord:
        candidate: Path | None = None
        extracted: PdfExtractedDocument | None = None
        inspection: PdfInspection | None = None
        try:
            self.repository.update(job.id, JobStatus.PROCESSING)
            manifest.update("reading")
            self._stage(stage_callback, "Inspecting PDF")
            inspection = handler.inspect(path)
            if inspection.encrypted or not inspection.supported:
                raise PdfUnsupportedError(inspection.rejection_codes or ["ENCRYPTED_PDF"])
            extracted = handler.extract(path)
            self.repository.update(job.id, JobStatus.ANALYZING)
            manifest.update("detecting")
            self._stage(stage_callback, "Detecting")
            deterministic = await self.regex.detect(extracted.text, self.policy)
            chunked = await self.chunker.detect(extracted.text, self.policy, deterministic)
            merged = merge_findings(extracted.text, deterministic + chunked.findings)
            accepted = [finding for finding in merged.findings
                        if finding.confidence >= self.policy.threshold_for(finding.category)]
            self.repository.update(job.id, JobStatus.SANITIZING, findings_count=len(accepted))
            manifest.update("sanitizing")
            self._stage(stage_callback, "Mapping PDF redactions")
            pdf_sanitized = handler.sanitize(extracted, accepted)
            text_sanitized = sanitize_text(extracted.text, accepted, self.policy)
            manifest.update("writing")
            self._stage(stage_callback, "Applying PDF redactions")
            candidate = handler.write(pdf_sanitized,
                self.settings.temp_dir / f"{job.id}-clean.pdf")
            structural = handler.verify_output(candidate, extracted.page_count)
            extraction_checks = handler.verify_original_absence(candidate, accepted)
            structural["extraction_checks"] = extraction_checks
            structural["passed"] = bool(structural.get("passed")) and bool(
                extraction_checks.get("passed")
            )
            output_extracted = handler.extract_output(candidate)
            replaced = [finding for finding in accepted
                        if self.policy.actions[finding.category] in {Action.REPLACE, Action.REDACT}
                        or (self.policy.actions[finding.category] == Action.REVIEW
                            and self.policy.review_behavior.auto_replace)]
            review_findings = [finding for finding in accepted
                               if self.policy.actions[finding.category] == Action.REVIEW]
            allowed_review_values = ({finding.text for finding in review_findings}
                if self.policy.review_behavior.warn_only else None)
            self.repository.update(job.id, JobStatus.VERIFYING)
            manifest.update("verifying")
            self._stage(stage_callback, "Reopening and verifying PDF")
            verification = await self.verifier.verify(output_extracted.text, replaced,
                self.policy, self.settings.ollama_verify, allowed_review_values)
            review_quarantine = (bool(review_findings)
                and self.policy.review_behavior.quarantine
                and not self.policy.review_behavior.auto_replace)
            clean_result = bool(structural.get("passed")) and verification.passed and not review_quarantine
            status = JobStatus.COMPLETED if clean_result else JobStatus.QUARANTINED
            target = self.settings.spotless_dir if clean_result else self.settings.quarantine_dir
            output_path = move_generated(candidate, target, f"{path.stem}-clean.pdf")
            candidate = None
            moved = (move_original(path, self.settings.processed_dir)
                     if self.settings.archive_processed else path)
            completed = utcnow()
            report = AuditReport(job_id=job.id, source_filename=path.name,
                source_hash=digest, output_filename=output_path.name, status=status,
                started_at=started, completed_at=completed, model=self.settings.ollama_model,
                policy={"name": self.policy.name, "version": self.policy.version},
                findings_count=len(accepted),
                findings_by_category=dict(Counter(finding.category for finding in accepted)),
                findings_by_source=source_counts(accepted), replacements=text_sanitized.replacements,
                ambiguous_overlaps=merged.ambiguous, verification=verification,
                chunk_telemetry={"chunk_count": chunked.telemetry.chunk_count,
                    "average_chunk_duration": chunked.telemetry.average_chunk_duration,
                    "total_inference_duration": chunked.telemetry.total_inference_duration,
                    "retry_count": chunked.telemetry.retry_count,
                    "invalid_finding_count": chunked.telemetry.invalid_finding_count},
                document_type="pdf", page_count=extracted.page_count,
                extracted_character_count=extracted.extracted_character_count,
                mapped_findings_count=len(pdf_sanitized.mappings),
                redaction_rectangle_count=pdf_sanitized.redaction_rectangle_count,
                mapping_warnings=list(pdf_sanitized.mapping_warnings),
                pdf_replacement_mode=self.settings.pdf_replacement_mode,
                label_placement_fallbacks=self._telemetry_int(
                    pdf_sanitized.write_telemetry, "label_fallback_count"),
                pdf_security=self._pdf_security(extracted),
                structural_verification=structural,
                quarantine_reason=None if clean_result else self._pdf_quarantine_reason(
                    structural, verification, review_quarantine))
            report_path, _ = self.reports.write(path.stem, report)
            result = self.repository.update(job.id, status, output_path=str(output_path),
                source_path=str(moved), report_path=str(report_path),
                verification_result=clean_result, findings_count=len(accepted))
            manifest.close()
            return result
        except PdfError as exc:
            if candidate and candidate.exists():
                candidate.unlink()
            moved = move_original(path, self.settings.processed_dir) if path.exists() else path
            return self._finish_pdf_problem(job, path, digest, started, manifest, moved,
                JobStatus.QUARANTINED, type(exc).__name__, extracted, inspection)
        except Exception as exc:
            if candidate and candidate.exists():
                candidate.unlink()
            LOG.error("job=%s file=%s failed code=%s", job.id, path.name, type(exc).__name__)
            moved = move_original(path, self.settings.failed_dir) if path.exists() else path
            return self._finish_pdf_problem(job, path, digest, started, manifest, moved,
                JobStatus.FAILED, type(exc).__name__, extracted, inspection)

    def _finish_pdf_problem(self, job: JobRecord, path: Path, digest: str,
                            started: datetime, manifest: JobManifest, moved: Path,
                            status: JobStatus, code: str,
                            extracted: PdfExtractedDocument | None,
                            inspection: PdfInspection | None) -> JobRecord:
        verification = VerificationReport(passed=False, remaining_findings_count=0,
                                          error_code=code)
        report = AuditReport(job_id=job.id, source_filename=path.name, source_hash=digest,
            output_filename=None, status=status, started_at=started, completed_at=utcnow(),
            model=self.settings.ollama_model,
            policy={"name": self.policy.name, "version": self.policy.version},
            findings_count=0, findings_by_category={}, replacements=[],
            verification=verification, error={"code": code,
                "message": "PDF processing stopped safely"}, document_type="pdf",
            page_count=extracted.page_count if extracted else (
                inspection.page_count if inspection else None),
            extracted_character_count=extracted.extracted_character_count if extracted else (
                inspection.extracted_character_count if inspection else 0),
            pdf_security=self._pdf_security(extracted, inspection, sanitized=False),
            quarantine_reason=code if status == JobStatus.QUARANTINED else None)
        report_path, _ = self.reports.write(f"{path.stem}-error", report)
        result = self.repository.update(job.id, status, source_path=str(moved),
            report_path=str(report_path), verification_result=False,
            error_code=code, error_message="PDF processing stopped safely")
        manifest.close()
        return result

    @staticmethod
    def _pdf_security(extracted: PdfExtractedDocument | None,
                      inspection: PdfInspection | None = None,
                      sanitized: bool = True) -> dict[str, object]:
        inspection = extracted.inspection if extracted is not None else inspection
        return {} if inspection is None else {
            "metadata_removed": sanitized,
            "annotations_removed": inspection.annotations_found if sanitized else 0,
            "embedded_files_found": inspection.embedded_files_found,
            "javascript_found": inspection.javascript_found,
            "forms_found": inspection.forms_found,
            "external_actions_found": inspection.external_actions_found,
            "appears_scanned": inspection.appears_scanned,
        }

    @staticmethod
    def _pdf_quarantine_reason(structural: dict[str, object],
                               verification: VerificationReport,
                               review_quarantine: bool) -> str:
        if not structural.get("passed"):
            return "PDF_STRUCTURAL_VERIFICATION_FAILED"
        if not verification.passed:
            return verification.error_code or "PDF_TEXT_VERIFICATION_FAILED"
        if review_quarantine:
            return "POLICY_REVIEW_REQUIRED"
        return "PDF_VERIFICATION_FAILED"

    @staticmethod
    def _telemetry_int(telemetry: dict[str, object], key: str) -> int:
        value = telemetry.get(key, 0)
        return value if isinstance(value, int) else 0

    @staticmethod
    def _stage(callback: Callable[[str], None] | None, stage: str) -> None:
        if callback is not None:
            callback(stage)
