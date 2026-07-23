import json
from pathlib import Path

from cleanroom.files.lifecycle import atomic_write_text


class JobManifest:
    def __init__(self, directory: Path, job_id: str, filename: str) -> None:
        self.directory, self.job_id, self.filename = directory, job_id, filename
        self.path: Path | None = None

    def update(self, stage: str) -> None:
        payload = json.dumps({"job_id": self.job_id, "filename": self.filename,
                              "stage": stage}, sort_keys=True) + "\n"
        if self.path and self.path.exists():
            self.path.unlink()
        self.path = atomic_write_text(self.directory, f"{self.job_id}.json", payload)

    def close(self) -> None:
        if self.path and self.path.exists():
            self.path.unlink()


def clean_manifests(directory: Path) -> int:
    if not directory.exists():
        return 0
    removed = 0
    for path in directory.glob("*.json"):
        if path.is_file() and not path.is_symlink():
            path.unlink()
            removed += 1
    return removed
