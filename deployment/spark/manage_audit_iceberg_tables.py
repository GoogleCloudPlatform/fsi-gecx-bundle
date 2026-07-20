"""Apply and verify lifecycle management for the audit Iceberg tables."""

from __future__ import annotations

import argparse
import datetime as dt
import json

from pyspark.sql import SparkSession


TABLES = (
    "compliance_audit.audit_events",
    "financial_ledger.account_ledger_entries",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-catalog", default="audit")
    parser.add_argument("--history-hours", type=int, default=6)
    parser.add_argument("--retain-last", type=int, default=60)
    args = parser.parse_args()
    if args.history_hours < 1:
        parser.error("--history-hours must be at least 1")
    if args.retain_last < 1:
        parser.error("--retain-last must be at least 1")

    spark = SparkSession.builder.appName("manage-audit-iceberg-tables").getOrCreate()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=args.history_hours)
    cutoff_sql = cutoff.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    max_snapshot_age_ms = args.history_hours * 60 * 60 * 1000
    results: dict[str, dict[str, object]] = {}

    for relative_name in TABLES:
        full_name = f"{args.audit_catalog}.{relative_name}"
        before = spark.table(f"{full_name}.snapshots").count()

        # Expire history first. This also makes the command usable when the
        # current metadata document is already close to the catalog limit.
        spark.sql(
            f"CALL {args.audit_catalog}.system.expire_snapshots("
            f"table => '{relative_name}', "
            f"older_than => TIMESTAMP '{cutoff_sql}', "
            f"retain_last => {args.retain_last})"
        ).collect()

        spark.sql(
            f"ALTER TABLE {full_name} SET TBLPROPERTIES ("
            "'gcp.biglake.table-management.enabled'='true',"
            f"'history.expire.max-snapshot-age-ms'='{max_snapshot_age_ms}',"
            f"'history.expire.min-snapshots-to-keep'='{args.retain_last}',"
            "'write.metadata.delete-after-commit.enabled'='true',"
            "'write.metadata.previous-versions-max'='20')"
        )
        after = spark.table(f"{full_name}.snapshots").count()
        properties = {
            row.key: row.value
            for row in spark.sql(f"SHOW TBLPROPERTIES {full_name}").collect()
        }
        results[relative_name] = {
            "snapshots_before": before,
            "snapshots_after": after,
            "table_management": properties.get("gcp.biglake.table-management.enabled"),
            "max_snapshot_age_ms": properties.get("history.expire.max-snapshot-age-ms"),
            "min_snapshots_to_keep": properties.get(
                "history.expire.min-snapshots-to-keep"
            ),
        }

    print("ICEBERG_TABLE_MANAGEMENT=" + json.dumps(results, sort_keys=True))
    if any(result["table_management"] != "true" for result in results.values()):
        raise RuntimeError(f"Automatic table management was not enabled: {results}")


if __name__ == "__main__":
    main()
