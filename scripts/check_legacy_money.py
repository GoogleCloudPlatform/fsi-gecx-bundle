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

"""Reject new/changed legacy monetary source lines outside the reviewed baseline.

The baseline can shrink: deleted lines do not need an adapter to be retained.
Changing a line containing a legacy symbol requires an explicit baseline review.
"""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts/legacy_money_allowlist.json"
ROOTS = ("banking-service/", "banking-ui/", "data-generator/", "adk-agent/",
         "gecx/", "deployment/", "scripts/datastream/")
EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".sql", ".json", ".yaml", ".yml"}
SYMBOL = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*_cents\b")


def inventory(root: Path) -> dict:
    # Include untracked source so an uncommitted addition cannot bypass the check.
    paths = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    ).decode().split("\0")
    result = {}
    for name in sorted(set(paths)):
        path = root / name
        if not name.startswith(ROOTS) or path.suffix not in EXTENSIONS or not path.is_file():
            continue
        lines = Counter()
        symbols = set()
        for line in path.read_text().splitlines():
            matches = SYMBOL.findall(line)
            if matches:
                # Ignore indentation only; every other source change is reviewed.
                lines[hashlib.sha256(line.strip().encode()).hexdigest()] += 1
                symbols.update(matches)
        if lines:
            result[name] = {"lines": dict(sorted(lines.items())), "symbols": sorted(symbols)}
    return result


def violations(actual: dict, baseline: dict) -> list[str]:
    errors = []
    for path, entry in actual.items():
        allowed = baseline.get(path, {})
        if not allowed.get("owner") or not allowed.get("rationale"):
            errors.append(f"{path}: missing reviewed owner/rationale")
        for fingerprint, count in entry["lines"].items():
            if count > allowed.get("lines", {}).get(fingerprint, 0):
                errors.append(f"{path}: unlisted or expanded legacy usage {fingerprint[:12]}")
    return errors


def main() -> int:
    baseline = json.loads(BASELINE.read_text())["files"]
    errors = violations(inventory(ROOT), baseline)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Legacy Money usage is within the reviewed baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
