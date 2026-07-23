import hashlib
import json
import statistics
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from cleanroom.detectors.merge import merge_findings
from cleanroom.detectors.regex_detector import RegexDetector
from cleanroom.files.pdf_handler import PdfDocumentHandler, create_synthetic_pdf
from cleanroom.models.finding import Finding
from cleanroom.models.policy import Action, SanitizationPolicy
from cleanroom.providers.base import ProviderError
from cleanroom.sanitizers.text_sanitizer import sanitize_text
from cleanroom.services.chunking import ChunkedDetector
from cleanroom.services.verification_service import VerificationService


@dataclass(frozen=True)
class EvaluationSummary:
    precision: float
    recall: float
    f1: float
    required_finding_recall: float
    exact_span_accuracy: float
    overlap_accuracy: float
    category_accuracy: float
    false_positives: int
    false_negatives: int
    invalid_model_findings: int
    average_latency: float
    median_latency: float
    p95_latency: float
    verification_pass_rate: float
    quarantine_rate: float
    case_count: int
    text_case_count: int = 0
    pdf_case_count: int = 0
    pdf_exact_mapping_rate: float = 1.0
    pdf_successful_redaction_rate: float = 1.0
    pdf_verification_pass_rate: float = 1.0
    pdf_quarantine_rate: float = 0.0
    pdf_mapping_failure_rate: float = 0.0
    pdf_metadata_sanitization_success_rate: float = 1.0
    average_pdf_duration_per_page: float = 0.0


class EvaluationService:
    def __init__(self, regex: RegexDetector, chunker: ChunkedDetector,
                 policy: SanitizationPolicy,
                 pdf_handler: PdfDocumentHandler | None = None) -> None:
        self.regex, self.chunker, self.policy = regex, chunker, policy
        self.pdf_handler = pdf_handler

    async def evaluate(self, cases_dir: Path, expected_dir: Path, output_dir: Path,
                       detector: str = "combined") -> EvaluationSummary:
        tp = fp = fn = required_total = required_hit = invalid = 0
        latencies: list[float] = []
        exact_hits = category_hits = expected_total = 0
        verification_passes = quarantines = 0
        text_cases = pdf_cases = pdf_mapped = pdf_expected = 0
        pdf_redacted = pdf_verified = pdf_quarantined = pdf_mapping_failures = 0
        pdf_metadata_passes = pdf_pages = 0
        pdf_durations: list[float] = []
        case_results: list[dict[str, object]] = []
        cases: list[tuple[str, str, list[dict[str, object]], str, Path | None, int]] = []
        for case_path in sorted(cases_dir.glob("*.txt")):
            expected = json.loads(
                (expected_dir / f"{case_path.stem}.json").read_text()
            )["findings"]
            cases.append((case_path.name, case_path.read_text(encoding="utf-8"),
                          expected, "text", None, 0))
        temporary_pdf: tempfile.TemporaryDirectory[str] | None = None
        if self.pdf_handler and (expected_dir / "pdf-structured.json").is_file():
            temporary_pdf = tempfile.TemporaryDirectory(prefix="cleanroom-evaluation-")
            generated_pdf = Path(temporary_pdf.name) / "pdf-structured.pdf"
            create_synthetic_pdf(generated_pdf)
            extracted = self.pdf_handler.extract(generated_pdf)
            expected = json.loads(
                (expected_dir / "pdf-structured.json").read_text()
            )["findings"]
            cases.append(("pdf-structured.pdf", extracted.text, expected,
                          "pdf", generated_pdf, extracted.page_count))
        for case_name, text, expected, document_type, case_pdf_path, page_count in cases:
            started = time.monotonic()
            deterministic = await self.regex.detect(text, self.policy) if detector in {"regex", "combined"} else []
            contextual: list[Finding] = []
            provider_error: str | None = None
            if detector in {"ollama", "combined"}:
                try:
                    chunked = await self.chunker.detect(text, self.policy, deterministic)
                    contextual = chunked.findings
                    invalid += chunked.telemetry.invalid_finding_count
                except ProviderError as exc:
                    invalid += 1
                    provider_error = type(exc).__name__
            found = merge_findings(text, deterministic + contextual).findings
            accepted = [item for item in found
                        if item.confidence >= self.policy.threshold_for(item.category)]
            sanitized = sanitize_text(text, accepted, self.policy)
            replaced = [item for item in accepted
                        if self.policy.actions[item.category] in {Action.REPLACE, Action.REDACT}]
            verification = await VerificationService(self.regex).verify(
                sanitized.text, replaced, self.policy, False)
            review_quarantine = any(self.policy.actions[item.category] == Action.REVIEW
                                    for item in accepted) and self.policy.review_behavior.quarantine
            pdf_details: dict[str, object] = {}
            if document_type == "pdf" and self.pdf_handler and case_pdf_path:
                pdf_cases += 1
                pdf_pages += page_count
                try:
                    extracted = self.pdf_handler.extract(case_pdf_path)
                    sanitized_pdf = self.pdf_handler.sanitize(extracted, accepted)
                    pdf_expected += len(accepted)
                    pdf_mapped += len(sanitized_pdf.mappings)
                    destination = case_pdf_path.with_name("pdf-structured-clean.pdf")
                    output = self.pdf_handler.write(sanitized_pdf, destination)
                    structural = self.pdf_handler.verify_output(output, page_count)
                    absence = self.pdf_handler.verify_original_absence(output, replaced)
                    pdf_redacted += bool(absence.get("passed"))
                    pdf_verified += bool(structural.get("passed")) and bool(absence.get("passed"))
                    pdf_metadata_passes += bool(structural.get("metadata_sanitized"))
                    pdf_details = {"mapped_findings": len(sanitized_pdf.mappings),
                                   "redaction_passed": bool(absence.get("passed")),
                                   "structural_verification_passed": bool(structural.get("passed"))}
                except Exception as exc:
                    pdf_mapping_failures += 1
                    pdf_quarantined += 1
                    pdf_details = {"mapping_error": type(exc).__name__}
            else:
                text_cases += 1
            verification_passes += verification.passed
            quarantines += (not verification.passed or review_quarantine)
            elapsed = time.monotonic() - started
            latencies.append(elapsed)
            if document_type == "pdf":
                pdf_durations.append(elapsed)
            found_keys = {(item.category.value, item.start, item.end) for item in found}
            expected_keys = {(item["category"], item["start"], item["end"]) for item in expected}
            required_keys = {(item["category"], item["start"], item["end"]) for item in expected
                             if item.get("required", True)}
            hits = found_keys & expected_keys
            tp += len(hits)
            fp += len(found_keys - expected_keys)
            fn += len(required_keys - found_keys)
            required_total += len(required_keys)
            required_hit += len(found_keys & required_keys)
            expected_total += len(expected_keys)
            exact_hits += len(hits)
            category_hits += len(hits)
            case_results.append({"case": case_name, "document_type": document_type,
                "source_hash": hashlib.sha256(text.encode()).hexdigest(),
                "found_count": len(found), "expected_count": len(expected), "true_positives": len(hits),
                "false_positives": len(found_keys - expected_keys), "false_negatives": len(required_keys - found_keys),
                "provider_error": provider_error, **pdf_details})
        if temporary_pdf is not None:
            temporary_pdf.cleanup()
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / expected_total if expected_total else 1.0
        required_recall = required_hit / required_total if required_total else 1.0
        summary = EvaluationSummary(precision, recall,
            2 * precision * recall / (precision + recall) if precision + recall else 0,
            required_recall, exact_hits / expected_total if expected_total else 1,
            exact_hits / expected_total if expected_total else 1,
            category_hits / expected_total if expected_total else 1, fp, fn, invalid,
            statistics.mean(latencies) if latencies else 0,
            statistics.median(latencies) if latencies else 0,
            _percentile(latencies, .95),
            verification_passes / len(case_results) if case_results else 1,
            quarantines / len(case_results) if case_results else 0,
            len(case_results), text_cases, pdf_cases,
            pdf_mapped / pdf_expected if pdf_expected else 1,
            pdf_redacted / pdf_cases if pdf_cases else 1,
            pdf_verified / pdf_cases if pdf_cases else 1,
            pdf_quarantined / pdf_cases if pdf_cases else 0,
            pdf_mapping_failures / pdf_cases if pdf_cases else 0,
            pdf_metadata_passes / pdf_cases if pdf_cases else 1,
            (sum(pdf_durations) / pdf_pages) if pdf_pages else 0)
        output_dir.mkdir(parents=True, exist_ok=True)
        data = summary.__dict__
        (output_dir / "summary.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        (output_dir / "summary.md").write_text(_summary_markdown(summary))
        cases_output = output_dir / "cases"
        cases_output.mkdir(exist_ok=True)
        for result in case_results:
            (cases_output / f"{Path(str(result['case'])).stem}.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n")
        return summary


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percentile))]


def _summary_markdown(summary: EvaluationSummary) -> str:
    return ("# Cleanroom Evaluation\n\n"
            f"- Precision: {summary.precision:.3f}\n- Recall: {summary.recall:.3f}\n"
            f"- F1: {summary.f1:.3f}\n- Required recall: {summary.required_finding_recall:.3f}\n"
            f"- False positives: {summary.false_positives}\n- False negatives: {summary.false_negatives}\n"
            f"- Invalid model responses/findings: {summary.invalid_model_findings}\n"
            f"- Average latency: {summary.average_latency:.4f}s\n\n"
            "## PDF metrics\n\n"
            f"- PDF cases: {summary.pdf_case_count}\n"
            f"- Exact mapping rate: {summary.pdf_exact_mapping_rate:.3f}\n"
            f"- Successful redaction rate: {summary.pdf_successful_redaction_rate:.3f}\n"
            f"- Verification pass rate: {summary.pdf_verification_pass_rate:.3f}\n"
            f"- Mapping failure rate: {summary.pdf_mapping_failure_rate:.3f}\n"
            f"- Metadata sanitization success: "
            f"{summary.pdf_metadata_sanitization_success_rate:.3f}\n"
            f"- Average duration per page: {summary.average_pdf_duration_per_page:.4f}s\n")
