#!/usr/bin/env python3

import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ID = os.environ.get("PROJECT_ID")
REGION = os.environ.get("REGION", "us-central1")
STREAM_ID = os.environ.get("DATASTREAM_STREAM_ID", "banking-alloydb-oltp-cdc-stream")
SOURCE_DATASET = os.environ.get("SOURCE_DATASET", "oltp_cdc")
CURATED_DATASET = os.environ.get("CURATED_DATASET", "analytics_curated")
VIEW_ROOT = Path(os.environ.get("VIEW_ROOT", "/app/deployment/bigquery/analytics_curated"))
MANIFEST = Path(os.environ.get("VIEW_MANIFEST", VIEW_ROOT / "views.json"))
VIEW_DIR = VIEW_ROOT / "view"


def run(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def log(message: str) -> None:
    print(message, flush=True)


def require_project_id() -> None:
    global PROJECT_ID
    if PROJECT_ID:
        return
    result = run(["gcloud", "config", "get-value", "project"])
    PROJECT_ID = result.stdout.strip()
    if not PROJECT_ID:
        log("PROJECT_ID is required for lakehouse view reconciliation.")
        sys.exit(2)


def ensure_stream_running() -> bool:
    describe = run(
        [
            "gcloud",
            "datastream",
            "streams",
            "describe",
            STREAM_ID,
            "--location",
            REGION,
            "--format=value(state)",
        ]
    )
    if describe.returncode != 0:
        log(f"Datastream stream {STREAM_ID} was not found or could not be described.")
        log(describe.stderr.strip())
        return False

    state = describe.stdout.strip()
    if state == "RUNNING":
        log(f"Datastream stream {STREAM_ID} is RUNNING.")
        return True

    log(f"Datastream stream {STREAM_ID} is {state or 'UNKNOWN'}; requesting RUNNING state.")
    update = run(
        [
            "gcloud",
            "datastream",
            "streams",
            "update",
            STREAM_ID,
            "--location",
            REGION,
            "--state=RUNNING",
            "--update-mask=state",
        ]
    )
    if update.returncode != 0:
        log(f"Unable to start Datastream stream {STREAM_ID}.")
        log(update.stderr.strip())
        return False
    return True


def source_is_queryable(source: str) -> tuple[bool, str | None]:
    if "." not in source:
        return False, "source must be formatted as dataset.table"
    query = f"SELECT 1 FROM `{PROJECT_ID}.{source}` LIMIT 0"
    result = run(
        [
            "bq",
            "query",
            f"--project_id={PROJECT_ID}",
            "--quiet",
            "--use_legacy_sql=false",
            "--format=none",
            query,
        ]
    )
    if result.returncode == 0:
        return True, None
    detail = result.stderr.strip() or result.stdout.strip()
    return False, detail


def apply_view(view: dict) -> tuple[bool, str | None]:
    sql_file = VIEW_DIR / view["sql"]
    if not sql_file.exists():
        return False, f"SQL file does not exist: {sql_file}"

    sql = sql_file.read_text(encoding="utf-8").replace("__PROJECT_ID__", PROJECT_ID)
    result = run(
        [
            "bq",
            "query",
            f"--project_id={PROJECT_ID}",
            "--quiet",
            "--use_legacy_sql=false",
        ],
        input_text=sql,
    )
    if result.returncode == 0:
        return True, None
    detail = result.stderr.strip() or result.stdout.strip()
    return False, detail


def load_manifest() -> list[dict]:
    with MANIFEST.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    views = payload.get("views", [])
    if not isinstance(views, list):
        raise ValueError("views.json must contain a top-level views array")
    return views


def main() -> int:
    require_project_id()
    log(f"Reconciling curated lakehouse views in {PROJECT_ID}.{CURATED_DATASET}.")

    try:
        views = load_manifest()
    except Exception as exc:
        log(f"Unable to load view manifest {MANIFEST}: {exc}")
        return 2

    stream_ready = ensure_stream_running()
    applied: list[str] = []
    skipped: dict[str, list[str]] = {}
    failed: dict[str, str] = {}

    for view in views:
        name = view.get("name")
        sources = view.get("sources", [])
        if not name or not view.get("sql") or not isinstance(sources, list):
            failed[str(name or "<unnamed>")] = "view entry must include name, sql, and sources"
            continue

        missing = []
        for source in sources:
            ready, reason = source_is_queryable(source)
            if not ready:
                missing.append(f"{source}: {reason}")

        if missing:
            skipped[name] = missing
            log(f"Skipping {name}; source tables are not queryable yet.")
            continue

        ok, reason = apply_view(view)
        if ok:
            applied.append(name)
            log(f"Applied curated view {CURATED_DATASET}.{name}.")
        else:
            failed[name] = reason or "unknown BigQuery error"
            log(f"Failed to apply curated view {CURATED_DATASET}.{name}.")

    summary = {
        "stream_ready": stream_ready,
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
    }
    log(json.dumps(summary, indent=2, sort_keys=True))

    if failed:
        return 1
    if not stream_ready:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
