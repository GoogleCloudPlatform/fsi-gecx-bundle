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

"""Regenerate (or --check) the committed credit knowledge corpus snapshot.

Run from banking-service/ after any change to resources/data/credit_products.json
or resources/knowledge/credit/policies.json:

    uv run python scripts/generate_credit_knowledge_corpus.py          # write
    uv run python scripts/generate_credit_knowledge_corpus.py --check  # CI
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.credit_knowledge_corpus import (  # noqa: E402
    CORPUS_DIR,
    generate_committed_corpus_files,
    stale_corpus_files,
    write_corpus_files,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed corpus is stale")
    args = parser.parse_args(argv)
    if args.check:
        stale = stale_corpus_files()
        if stale:
            print(
                f"Credit knowledge corpus is stale: {', '.join(stale)}. Run "
                "`uv run python scripts/generate_credit_knowledge_corpus.py` in banking-service/.",
                file=sys.stderr,
            )
            return 1
        print("Credit knowledge corpus is fresh.")
        return 0
    write_corpus_files(generate_committed_corpus_files())
    print(f"Wrote credit knowledge corpus to {CORPUS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
