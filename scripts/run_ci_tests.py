#!/usr/bin/env python3
"""Run pytest and expose process-level failures through GitHub Checks."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print(result.stdout, end="")
    if result.returncode:
        tail = result.stdout[-6000:]
        if os.environ.get("GITHUB_ACTIONS") == "true":
            escaped = tail.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            print(f"::error title=pytest process failed::{escaped}")
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
