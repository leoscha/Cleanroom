import os
from pathlib import Path


def discover_files(directory: Path, supported_extensions: set[str] | None = None) -> list[Path]:
    if not directory.is_dir():
        return []
    result: list[Path] = []
    extensions = supported_extensions or {".txt"}
    for entry in sorted(directory.iterdir()):
        name = entry.name
        if name.startswith(".") or name.startswith("~") or name.endswith((".tmp", ".part", ".swp")):
            continue
        if entry.is_symlink() or entry.suffix.lower() not in extensions:
            continue
        try:
            if entry.is_file() and not os.path.islink(entry):
                result.append(entry)
        except OSError:
            continue
    return result
