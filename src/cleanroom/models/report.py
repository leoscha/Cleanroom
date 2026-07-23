from datetime import datetime

from pydantic import BaseModel, Field

from cleanroom.models.finding import Category
from cleanroom.models.job import JobStatus


class ReplacementReport(BaseModel):
    category: Category
    original_hash: str
    placeholder: str
    sources: list[str]
    confidence: float


class VerificationReport(BaseModel):
    passed: bool
    remaining_findings_count: int
    original_values_remaining: int = 0
    deterministic_remaining_findings: int = 0
    ollama_remaining_findings: int = 0
    ignored_placeholder_findings: int = 0
    ignored_policy_review_findings: int = 0
    malformed_placeholders: int = 0
    error_code: str | None = None
    categories: dict[Category, int] = Field(default_factory=dict)


class AuditReport(BaseModel):
    job_id: str
    source_filename: str
    source_hash: str
    output_filename: str | None
    status: JobStatus
    started_at: datetime
    completed_at: datetime
    model: str
    policy: dict[str, str | int]
    findings_count: int
    findings_by_category: dict[Category, int]
    findings_by_source: dict[str, int] = Field(default_factory=dict)
    replacements: list[ReplacementReport]
    review_findings: list[dict[str, str | float]] = Field(default_factory=list)
    ambiguous_overlaps: list[dict[str, str | int | float]] = Field(default_factory=list)
    verification: VerificationReport
    markdown_report_path: str | None = None
    chunk_telemetry: dict[str, int | float] = Field(default_factory=dict)
    error: dict[str, str] | None = None
    document_type: str = "text"
    page_count: int | None = None
    extracted_character_count: int = 0
    mapped_findings_count: int = 0
    redaction_rectangle_count: int = 0
    mapping_warnings: list[str] = Field(default_factory=list)
    pdf_replacement_mode: str | None = None
    label_placement_fallbacks: int = 0
    pdf_security: dict[str, object] = Field(default_factory=dict)
    structural_verification: dict[str, object] = Field(default_factory=dict)
    quarantine_reason: str | None = None
