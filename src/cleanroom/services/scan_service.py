from dataclasses import dataclass
from pathlib import Path

from cleanroom.database.models import JobRecord
from cleanroom.files.discovery import discover_files
from cleanroom.services.processing_service import DuplicateFileError, ProcessingService


@dataclass
class ScanResult:
    discovered: int
    jobs: list[JobRecord]
    duplicates_skipped: int


class ScanService:
    def __init__(self, processing: ProcessingService, dirty_dir: Path,
                 supported_extensions: set[str] | None = None) -> None:
        self.processing, self.dirty_dir = processing, dirty_dir
        self.supported_extensions = supported_extensions or {".txt"}

    async def scan(self) -> ScanResult:
        files = discover_files(self.dirty_dir, self.supported_extensions)
        jobs: list[JobRecord] = []
        skipped = 0
        for path in files:
            try:
                jobs.append(await self.processing.process(path))
            except DuplicateFileError:
                skipped += 1
        return ScanResult(len(files), jobs, skipped)
