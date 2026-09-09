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

"""Archive a read-only Money report before applying the additive migration."""

import argparse
import json
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.money_reconciliation import reconcile_money, migration_blockers  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Use the application's connector for IAM and attached SQLite schemas.
    from utils.database import create_db_engine
    engine = create_db_engine(os.environ["DATABASE_URL"])
    if engine.dialect.name == "postgresql":
        engine = engine.execution_options(isolation_level="REPEATABLE READ")
    with engine.connect() as connection:
        report = reconcile_money(connection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(f"Wrote Money reconciliation to {args.output}; blockers={len(migration_blockers(report))}")
    raise SystemExit(1 if migration_blockers(report) else 0)


if __name__ == "__main__":
    main()
