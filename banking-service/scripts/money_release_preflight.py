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

"""Archive Money reconciliation in the demo environment without resetting data."""

import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("DISABLE_INIT_DB", "true")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-gcs", help="Unique gs://bucket/object.json.gz report destination")
    parser.add_argument("--pause-writes", action="store_true")
    parser.add_argument("--resume-writes", action="store_true")
    args = parser.parse_args()
    if args.pause_writes and args.resume_writes:
        parser.error("Choose either pause or resume")
    from utils.maintenance import enable_maintenance_mode, disable_maintenance_mode, is_maintenance_mode
    if args.resume_writes:
        disable_maintenance_mode()
        if is_maintenance_mode():
            raise RuntimeError("Maintenance mode did not clear")
        print(json.dumps({"money_release": "writes_resumed"}), flush=True)
        return
    if not args.output_gcs or not args.output_gcs.startswith("gs://"):
        parser.error("A gs:// report destination is required")
    if args.pause_writes:
        if not enable_maintenance_mode(reason="MONEY_FOUNDATION_MIGRATION",
            message="Money foundation maintenance is in progress. Please retry shortly.", ttl_seconds=1800):
            raise RuntimeError("Could not pause demo writes")
    from utils.database import create_db_engine
    from services.money_reconciliation import reconcile_money, migration_blockers
    engine = create_db_engine(os.environ["DATABASE_URL"])
    if engine.dialect.name == "postgresql":
        engine = engine.execution_options(isolation_level="REPEATABLE READ")
    with engine.connect() as connection:
        connection.info["_ignore_rbac"] = True
        report = reconcile_money(connection)
    report["captured_at"] = datetime.now(timezone.utc).isoformat()
    from utils.version import BUILD_COMMIT_ID
    report["release_commit"] = BUILD_COMMIT_ID
    path = Path("/tmp/money-reconciliation.json.gz")
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(report, stream, default=str)
    from google.cloud import storage
    bucket, object_name = args.output_gcs[5:].split("/", 1)
    storage.Client().bucket(bucket).blob(object_name).upload_from_filename(
        str(path), content_type="application/gzip", if_generation_match=0)
    blockers = migration_blockers(report)
    print(json.dumps({"money_release": "preflight", "report": args.output_gcs,
        "release_commit": BUILD_COMMIT_ID, "counts": report["counts"],
        "blockers": {key: len(value) for key, value in blockers.items()},
        "balance_differences": len(report["balance_differences"]),
        "writes_paused": args.pause_writes}), flush=True)
    raise SystemExit(1 if blockers else 0)


if __name__ == "__main__":
    main()
