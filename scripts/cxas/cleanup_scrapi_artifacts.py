#!/usr/bin/env python3
"""Delete only the repository's dedicated local SCRAPI artifact directory."""

from __future__ import annotations

import shutil
from pathlib import Path


ARTIFACT_DIR = Path(__file__).resolve().parent / ".artifacts"


def main() -> int:
    expected_parent = Path(__file__).resolve().parent
    artifact_dir = ARTIFACT_DIR.resolve()
    if artifact_dir.parent != expected_parent or artifact_dir.name != ".artifacts":
        raise RuntimeError(f"Refusing to clean unexpected path: {artifact_dir}")

    if not artifact_dir.exists():
        print(f"No SCRAPI artifacts to remove: {artifact_dir}")
        return 0

    if not artifact_dir.is_dir():
        raise RuntimeError(f"Refusing to clean non-directory path: {artifact_dir}")

    file_count = sum(1 for path in artifact_dir.rglob("*") if path.is_file())
    shutil.rmtree(artifact_dir)
    print(f"Removed {file_count} SCRAPI artifact file(s): {artifact_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
