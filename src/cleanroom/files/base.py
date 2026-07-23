from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from cleanroom.models.finding import Finding


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    source_path: Path
    document_type: str = "text"
    page_count: int | None = None
    extracted_character_count: int = 0


@dataclass(frozen=True)
class SanitizedDocument:
    text: str
    source_path: Path
    document_type: str = "text"


ExtractedT = TypeVar("ExtractedT", bound=ExtractedDocument)
SanitizedT = TypeVar("SanitizedT", bound=SanitizedDocument)


class DocumentHandler(Protocol[ExtractedT, SanitizedT]):
    supported_extensions: set[str]

    def extract(self, path: Path) -> ExtractedT: ...

    def sanitize(self, document: ExtractedT,
                 findings: list[Finding]) -> SanitizedT: ...

    def write(self, document: SanitizedT, destination: Path) -> Path: ...

    def verify_output(self, path: Path, expected_page_count: int | None = None) -> dict[str, object]: ...
