import difflib
import json
from collections import Counter
from pathlib import Path

from cleanroom.files.lifecycle import atomic_write_text
from cleanroom.models.finding import Finding
from cleanroom.models.report import AuditReport


class ReportService:
    def __init__(self, reports_dir: Path, write_review_diff: bool = False) -> None:
        self.reports_dir = reports_dir
        self.write_review_diff = write_review_diff

    def write(self, stem: str, report: AuditReport, original: str | None = None,
              sanitized: str | None = None) -> tuple[Path, Path]:
        markdown = atomic_write_text(self.reports_dir, f"{stem}-report.md",
                                     self._markdown(report))
        report.markdown_report_path = str(markdown)
        content = json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        json_path = atomic_write_text(self.reports_dir, f"{stem}-report.json", content)
        if self.write_review_diff and original is not None and sanitized is not None:
            private = self.reports_dir / "private-review"
            diff = "".join(difflib.unified_diff(
                original.splitlines(keepends=True), sanitized.splitlines(keepends=True),
                fromfile="original-sensitive", tofile="sanitized"))
            atomic_write_text(private, f"{stem}-review.diff", diff)
        return json_path, markdown

    @staticmethod
    def _markdown(report: AuditReport) -> str:
        duration = (report.completed_at - report.started_at).total_seconds()
        category_lines = "\n".join(
            f"- {category.value}: {count}"
            for category, count in sorted(report.findings_by_category.items(), key=lambda item: item[0].value)
        ) or "- None"
        source_lines = "\n".join(
            f"- {source}: {count}" for source, count in sorted(report.findings_by_source.items())
        ) or "- None"
        verification = report.verification
        result = "Passed" if verification.passed else "Needs review"
        next_action = (
            "Review the quarantined output locally, then adjust the source or policy and retry."
            if report.status.value == "quarantined"
            else "No action is required; retain the report with the sanitized output."
        )
        pdf_section = ""
        if report.document_type == "pdf":
            pdf_section = f"""
## PDF processing

- Pages: {report.page_count}
- Extracted characters: {report.extracted_character_count}
- Mapped findings: {report.mapped_findings_count}
- Redaction rectangles: {report.redaction_rectangle_count}
- Replacement mode: {report.pdf_replacement_mode}
- Label fallbacks: {report.label_placement_fallbacks}
- Metadata sanitized: {report.structural_verification.get('metadata_sanitized', False)}
- Structural verification: {report.structural_verification.get('passed', False)}
- Quarantine reason: {report.quarantine_reason or 'None'}
"""
        return f"""# Cleanroom Report

## Result

Status: {report.status.value.title()}  
File: {report.source_filename}  
Output: {report.output_filename or "Not written"}  
Policy: {report.policy['name']} v{report.policy['version']}  
Model: {report.model}  
Started: {report.started_at.isoformat()}  
Completed: {report.completed_at.isoformat()}  
Duration: {duration:.3f} seconds

## Sanitization

Replacements: {len(report.replacements)}

### Findings by category

{category_lines}

### Findings by source

{source_lines}

## Verification

- Original values remaining: {verification.original_values_remaining}
- Deterministic findings remaining: {verification.deterministic_remaining_findings}
- Ollama findings remaining: {verification.ollama_remaining_findings}
- Ignored placeholder findings: {verification.ignored_placeholder_findings}
- Policy-allowed review findings: {verification.ignored_policy_review_findings}
- Malformed placeholders: {verification.malformed_placeholders}
- Result: {result}
{pdf_section}

## Safe next action

{next_action}
"""


def source_counts(findings: list[Finding]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for finding in findings:
        counts.update(finding.sources)
    return dict(counts)
