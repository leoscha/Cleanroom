from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from cleanroom.config.ollama_endpoint import (
    ConnectionMode,
    ValidatedEndpoint,
    validate_ollama_endpoint,
)

PDF_MODES = {"label", "black_box", "blank"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    dirty_dir: Path = Field(Path("./dirty"), alias="CLEANROOM_DIRTY_DIR")
    spotless_dir: Path = Field(Path("./spotless"), alias="CLEANROOM_SPOTLESS_DIR")
    processed_dir: Path = Field(Path("./processed"), alias="CLEANROOM_PROCESSED_DIR")
    failed_dir: Path = Field(Path("./failed"), alias="CLEANROOM_FAILED_DIR")
    reports_dir: Path = Field(Path("./reports"), alias="CLEANROOM_REPORTS_DIR")
    quarantine_dir: Path = Field(Path("./spotless/quarantine"), alias="CLEANROOM_QUARANTINE_DIR")
    database_url: str = Field("sqlite:///./cleanroom.db", alias="CLEANROOM_DATABASE_URL")
    policy_path: Path = Field(Path("./config/default-policy.yaml"), alias="CLEANROOM_POLICY_PATH")
    workspace_dir: Path = Field(Path("."), alias="CLEANROOM_WORKSPACE_DIR")
    temp_dir: Path = Field(Path("./.cleanroom/tmp"), alias="CLEANROOM_TEMP_DIR")
    ollama_connection_mode: ConnectionMode = Field(
        ConnectionMode.LOCAL, alias="OLLAMA_CONNECTION_MODE"
    )
    ollama_base_url: str = Field("http://127.0.0.1:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field("gemma3:4b", alias="OLLAMA_MODEL")
    ollama_timeout_seconds: float = Field(180, gt=0, alias="OLLAMA_TIMEOUT_SECONDS")
    ollama_max_retries: int = Field(2, ge=0, le=10, alias="OLLAMA_MAX_RETRIES")
    min_confidence: float = Field(0.70, ge=0, le=1, alias="CLEANROOM_MIN_CONFIDENCE")
    max_file_size_mb: int = Field(20, gt=0, alias="CLEANROOM_MAX_FILE_SIZE_MB")
    supported_extensions: str = Field(".txt,.pdf", alias="CLEANROOM_SUPPORTED_EXTENSIONS")
    file_stability_seconds: float = Field(3, ge=0, alias="CLEANROOM_FILE_STABILITY_SECONDS")
    chunk_max_chars: int = Field(12000, gt=100, alias="CLEANROOM_CHUNK_MAX_CHARS")
    chunk_overlap_chars: int = Field(500, ge=0, alias="CLEANROOM_CHUNK_OVERLAP_CHARS")
    max_chunks_per_file: int = Field(100, gt=0, alias="CLEANROOM_MAX_CHUNKS_PER_FILE")
    verify_output: bool = Field(True, alias="CLEANROOM_VERIFY_OUTPUT")
    ollama_verify: bool = Field(True, alias="CLEANROOM_OLLAMA_VERIFY")
    write_review_diff: bool = Field(False, alias="CLEANROOM_WRITE_REVIEW_DIFF")
    archive_processed: bool = Field(True, alias="CLEANROOM_ARCHIVE_PROCESSED")
    pdf_replacement_mode: str = Field("label", alias="CLEANROOM_PDF_REPLACEMENT_MODE")
    pdf_remove_metadata: bool = Field(True, alias="CLEANROOM_PDF_REMOVE_METADATA")
    pdf_remove_annotations: bool = Field(True, alias="CLEANROOM_PDF_REMOVE_ANNOTATIONS")
    pdf_reject_forms: bool = Field(True, alias="CLEANROOM_PDF_REJECT_FORMS")
    pdf_reject_embedded_files: bool = Field(True, alias="CLEANROOM_PDF_REJECT_EMBEDDED_FILES")
    pdf_reject_javascript: bool = Field(True, alias="CLEANROOM_PDF_REJECT_JAVASCRIPT")
    pdf_reject_images: bool = Field(True, alias="CLEANROOM_PDF_REJECT_IMAGES")
    pdf_min_text_chars_per_page: int = Field(20, ge=1,
        alias="CLEANROOM_PDF_MIN_TEXT_CHARS_PER_PAGE")
    pdf_mapping_min_confidence: float = Field(.95, ge=0, le=1,
        alias="CLEANROOM_PDF_MAPPING_MIN_CONFIDENCE")
    allow_public_ollama: bool = Field(False, alias="CLEANROOM_ALLOW_PUBLIC_OLLAMA")
    allow_insecure_remote_ollama: bool = Field(
        False, alias="CLEANROOM_ALLOW_INSECURE_REMOTE_OLLAMA"
    )
    eval_min_required_recall: float = Field(.95, ge=0, le=1, alias="CLEANROOM_EVAL_MIN_REQUIRED_RECALL")
    eval_min_precision: float = Field(.70, ge=0, le=1, alias="CLEANROOM_EVAL_MIN_PRECISION")
    eval_min_exact_span_accuracy: float = Field(.95, ge=0, le=1,
        alias="CLEANROOM_EVAL_MIN_EXACT_SPAN_ACCURACY")
    eval_min_verification_pass_rate: float = Field(1, ge=0, le=1,
        alias="CLEANROOM_EVAL_MIN_VERIFICATION_PASS_RATE")
    eval_max_invalid_findings: int = Field(0, ge=0,
        alias="CLEANROOM_EVAL_MAX_INVALID_FINDINGS")
    eval_min_pdf_mapping_rate: float = Field(1, ge=0, le=1,
        alias="CLEANROOM_EVAL_MIN_PDF_MAPPING_RATE")
    eval_min_pdf_redaction_rate: float = Field(1, ge=0, le=1,
        alias="CLEANROOM_EVAL_MIN_PDF_REDACTION_RATE")
    eval_min_pdf_verification_rate: float = Field(1, ge=0, le=1,
        alias="CLEANROOM_EVAL_MIN_PDF_VERIFICATION_RATE")
    log_level: str = Field("INFO", alias="CLEANROOM_LOG_LEVEL")
    api_host: str = Field("127.0.0.1", alias="CLEANROOM_API_HOST")

    @field_validator("ollama_base_url")
    @classmethod
    def private_ollama(cls, value: str) -> str:
        return value.rstrip("/")

    @model_validator(mode="after")
    def safe_network_and_chunks(self) -> "Settings":
        validate_ollama_endpoint(
            self.ollama_base_url,
            self.ollama_connection_mode,
            allow_public=self.allow_public_ollama,
            allow_insecure_remote=self.allow_insecure_remote_ollama,
        )
        if self.chunk_overlap_chars >= self.chunk_max_chars:
            raise ValueError("CLEANROOM_CHUNK_OVERLAP_CHARS must be smaller than chunk max")
        extensions = self.extension_set
        if not extensions or not extensions <= {".txt", ".pdf"}:
            raise ValueError("CLEANROOM_SUPPORTED_EXTENSIONS may contain only .txt and .pdf")
        if self.pdf_replacement_mode not in PDF_MODES:
            raise ValueError("CLEANROOM_PDF_REPLACEMENT_MODE must be label, black_box, or blank")
        return self

    @field_validator("api_host")
    @classmethod
    def localhost_api(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("API host must be loopback")
        return value

    @property
    def required_dirs(self) -> tuple[Path, ...]:
        return (self.dirty_dir, self.spotless_dir, self.processed_dir, self.failed_dir,
                self.reports_dir, self.quarantine_dir)

    @property
    def extension_set(self) -> set[str]:
        return {item.strip().lower() for item in self.supported_extensions.split(",") if item.strip()}

    @property
    def validated_ollama_endpoint(self) -> ValidatedEndpoint:
        return validate_ollama_endpoint(
            self.ollama_base_url,
            self.ollama_connection_mode,
            allow_public=self.allow_public_ollama,
            allow_insecure_remote=self.allow_insecure_remote_ollama,
        )
