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

"""Fail when a tracked source or configuration file lacks the Google header."""

from __future__ import annotations

from pathlib import Path
import subprocess


RELEVANT_SUFFIXES = {
    ".css",
    ".conf",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".jsx",
    ".mako",
    ".py",
    ".scss",
    ".sh",
    ".sql",
    ".tf",
    ".tfbackend",
    ".tfvars",
    ".toml",
    ".ts",
    ".tsx",
    ".xml",
    ".yaml",
    ".yml",
}
RELEVANT_NAMES = {"CODEOWNERS", "Dockerfile", "Makefile", "requirements.txt"}
REQUIRED_TEXT = (
    "Copyright 2026 Google LLC",
    'Licensed under the Apache License, Version 2.0 (the "License");',
    "https://www.apache.org/licenses/LICENSE-2.0",
    'distributed under the License is distributed on an "AS IS" BASIS,',
    "limitations under the License.",
)


def is_relevant(path: Path) -> bool:
    return (
        path.suffix in RELEVANT_SUFFIXES
        or path.name in RELEVANT_NAMES
        or path.name.endswith(".conf.template")
        or path.name.endswith(".yaml.disabled")
        or path.name.endswith(".yaml.tftpl")
    )


def tracked_files() -> list[Path]:
    output = subprocess.check_output(["git", "ls-files", "-z"])
    return [Path(item.decode()) for item in output.split(b"\0") if item]


def main() -> int:
    missing: list[str] = []
    for path in tracked_files():
        if not is_relevant(path):
            continue
        header = "\n".join(
            path.read_text(encoding="utf-8", errors="replace").splitlines()[:30]
        )
        if not all(required in header for required in REQUIRED_TEXT):
            missing.append(str(path))

    if missing:
        print("Missing or incomplete Google Apache license header:")
        for path in missing:
            print(f"  {path}")
        return 1
    print("All relevant tracked files contain the Google Apache license header.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
