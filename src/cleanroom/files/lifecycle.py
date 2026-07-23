import os
import tempfile
from contextlib import suppress
from pathlib import Path


def collision_safe(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 2
    while (candidate := directory / f"{stem}-{counter}{suffix}").exists():
        counter += 1
    return candidate


def atomic_write_text(directory: Path, filename: str, content: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = collision_safe(directory, filename)
    descriptor, temporary = tempfile.mkstemp(prefix=".cleanroom-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temporary)
        raise
    return destination


def move_original(source: Path, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = collision_safe(directory, source.name)
    os.replace(source, destination)
    return destination


def move_generated(source: Path, directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = collision_safe(directory, filename)
    os.replace(source, destination)
    return destination
