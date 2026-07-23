import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    pdf_min_text_chars_per_page: int = Field(20, ge=1,
        alias="CLEANROOM_PDF_MIN_TEXT_CHARS_PER_PAGE")
    pdf_mapping_min_confidence: float = Field(.95, ge=0, le=1,
        alias="CLEANROOM_PDF_MAPPING_MIN_CONFIDENCE")
    allow_public_ollama: bool = Field(False, alias="CLEANROOM_ALLOW_PUBLIC_OLLAMA")
    eval_min_required_recall: float = Field(.95, ge=0, le=1, alias="CLEANROOM_EVAL_MIN_REQUIRED_RECALL")
    eval_min_precision: float = Field(.70, ge=0, le=1, alias="CLEANROOM_EVAL_MIN_PRECISION")
    log_level: str = Field("INFO", alias="CLEANROOM_LOG_LEVEL")
    api_host: str = Field("127.0.0.1", alias="CLEANROOM_API_HOST")

    @field_validator("ollama_base_url")
    @classmethod
    def private_ollama(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("OLLAMA_BASE_URL must be an http(s) URL")
        return value.rstrip("/")

    @model_validator(mode="after")
    def safe_network_and_chunks(self) -> "Settings":
        kind = endpoint_network_kind(self.ollama_base_url)
        if kind in {"public", "hostname"} and not self.allow_public_ollama:
            raise ValueError(
                "OLLAMA_BASE_URL must be loopback, a private RFC1918 address, or Tailscale; "
                "set CLEANROOM_ALLOW_PUBLIC_OLLAMA=true only if you accept the risk"
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


def endpoint_network_kind(url: str) -> str:
    hostname = urlparse(url).hostname
    if hostname == "localhost":
        return "loopback"
    if hostname is None:
        return "invalid"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(item[4][0])
                         for item in socket.getaddrinfo(hostname, None)}
        except OSError:
            return "hostname"
        kinds = {_address_kind(address) for address in addresses}
        if "public" in kinds:
            return "public"
        return "tailscale" if "tailscale" in kinds else (
            "private" if "private" in kinds else "loopback")
    return _address_kind(address)


def _address_kind(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    if address.is_loopback:
        return "loopback"
    if address in ipaddress.ip_network("100.64.0.0/10"):
        return "tailscale"
    if address.is_private:
        return "private"
    return "public"
