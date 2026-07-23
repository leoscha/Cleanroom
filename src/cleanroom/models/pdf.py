from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from cleanroom.files.base import ExtractedDocument, SanitizedDocument
from cleanroom.models.finding import Finding

BBox = tuple[float, float, float, float]


class PdfTextSpan(BaseModel):
    page_number: int = Field(ge=1)
    text: str
    bbox: BBox
    block_index: int
    line_index: int
    span_index: int
    global_start: int = Field(ge=0)
    global_end: int = Field(ge=0)


class PdfInspection(BaseModel):
    page_count: int
    extracted_character_count: int
    encrypted: bool
    malformed: bool = False
    annotations_found: int = 0
    embedded_files_found: int = 0
    forms_found: bool = False
    javascript_found: bool = False
    external_actions_found: bool = False
    optional_content_found: bool = False
    metadata_present: bool = False
    image_count: int = 0
    pages_without_text: int = 0
    appears_scanned: bool = False
    supported: bool = True
    rejection_codes: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PdfCharRef:
    page_number: int
    block_index: int
    line_index: int
    span_index: int
    char_index: int
    bbox: BBox


@dataclass(frozen=True)
class PdfExtractedDocument(ExtractedDocument):
    document_type: str = "pdf"
    file_hash: str = ""
    page_count: int = 0
    extracted_character_count: int = 0
    page_text: tuple[str, ...] = ()
    spans: tuple[PdfTextSpan, ...] = ()
    char_map: tuple[PdfCharRef | None, ...] = ()
    inspection: PdfInspection | None = None
    warnings: tuple[str, ...] = ()
    extraction_confidence: float = 1.0


@dataclass(frozen=True)
class PdfRedactionMapping:
    finding: Finding
    placeholder: str
    rectangles: tuple[tuple[int, BBox], ...]
    confidence: float


@dataclass(frozen=True)
class PdfSanitizedDocument(SanitizedDocument):
    document_type: str = "pdf"
    extracted: PdfExtractedDocument | None = None
    mappings: tuple[PdfRedactionMapping, ...] = ()
    mapping_warnings: tuple[str, ...] = ()
    redaction_rectangle_count: int = 0
    label_fallback_count: int = 0
    write_telemetry: dict[str, object] = field(default_factory=dict)
