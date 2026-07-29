#!/usr/bin/env python3
"""Fail when a repository-local Markdown link points to a missing path."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    checked = 0
    for document in sorted(root.rglob("*.md")):
        if any(part.startswith(".") or part in {"build", "dist"} for part in document.relative_to(root).parts):
            continue
        for raw_target in LINK.findall(document.read_text(encoding="utf-8")):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            path_text = unquote(target.split("#", 1)[0])
            if not path_text:
                continue
            checked += 1
            candidate = (document.parent / path_text).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                failures.append(f"{document.relative_to(root)}: link escapes repository: {target}")
                continue
            if not candidate.exists():
                failures.append(f"{document.relative_to(root)}: missing target: {target}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"Validated {checked} repository-local Markdown links")


if __name__ == "__main__":
    main()
