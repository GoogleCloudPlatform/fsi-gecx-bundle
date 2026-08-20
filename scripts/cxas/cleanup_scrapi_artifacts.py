#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
