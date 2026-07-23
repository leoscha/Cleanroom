import asyncio
import hashlib
from pathlib import Path

from cleanroom.files.base import ExtractedDocument, SanitizedDocument
from cleanroom.files.lifecycle import atomic_write_text
from cleanroom.models.finding import Finding
from cleanroom.models.policy import SanitizationPolicy
from cleanroom.sanitizers.text_sanitizer import sanitize_text


class FileSafetyError(ValueError):
    pass


def validate_input(path: Path, root: Path, max_bytes: int,
                   supported_extensions: set[str] | None = None) -> Path:
    if not str(path):
        raise FileSafetyError("empty input path")
    if path.is_symlink():
        raise FileSafetyError("symlinks are not allowed")
    resolved, resolved_root = path.resolve(), root.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise FileSafetyError("input is outside the dirty directory")
    if not resolved.is_file():
        raise FileSafetyError("input must be a regular file")
    extensions = supported_extensions or {".txt"}
    if resolved.suffix.lower() not in extensions:
        raise FileSafetyError(
            f"unsupported file extension; allowed: {', '.join(sorted(extensions))}"
        )
    if resolved.stat().st_size > max_bytes:
        raise FileSafetyError("file exceeds configured maximum size")
    return resolved


async def wait_until_stable(path: Path, seconds: float) -> None:
    before = path.stat()
    await asyncio.sleep(seconds)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise FileSafetyError("file is still being copied")


def read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FileSafetyError("file is not valid UTF-8") from exc


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


class TextDocumentHandler:
    supported_extensions = {".txt"}

    def __init__(self, policy: SanitizationPolicy) -> None:
        self.policy = policy

    def extract(self, path: Path) -> ExtractedDocument:
        text = read_utf8(path)
        return ExtractedDocument(text, path, extracted_character_count=len(text))

    def sanitize(self, document: ExtractedDocument,
                 findings: list[Finding]) -> SanitizedDocument:
        result = sanitize_text(document.text, findings, self.policy)
        return SanitizedDocument(result.text, document.source_path)

    def write(self, document: SanitizedDocument, destination: Path) -> Path:
        return atomic_write_text(destination.parent, destination.name, document.text)

    def verify_output(self, path: Path, expected_page_count: int | None = None) -> dict[str, object]:
        read_utf8(path)
        return {"passed": True, "utf8_readable": True}
