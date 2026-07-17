"""Proves one Spark session can read audit Iceberg and native BigQuery CDC tables."""

from __future__ import annotations

import argparse
import json

from pyspark.sql import SparkSession, functions as F


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-catalog", default="audit")
    parser.add_argument("--bigquery-catalog", default="bq")
    args = parser.parse_args()

    spark = SparkSession.builder.appName("validate-lakehouse-catalog-interoperability").getOrCreate()
    ledger_name = f"{args.audit_catalog}.financial_ledger.account_ledger_entries"
    native_name = f"{args.bigquery_catalog}.iceberg_catalog.cards_credit_accounts"

    ledger = spark.table(ledger_name)
    native_accounts = spark.table(native_name)
    linked = ledger.withColumn(
        "credit_account_id",
        F.get_json_object(F.col("source_references"), "$.credit_account_id"),
    ).join(
        native_accounts,
        F.col("credit_account_id") == native_accounts["id"].cast("string"),
        "inner",
    )

    ledger_count = ledger.count()
    native_count = native_accounts.count()
    linked_count = linked.count()
    snapshots = spark.table(f"{ledger_name}.snapshots").count()
    files = spark.table(f"{ledger_name}.files").count()
    result = {
        "ledger_rows": ledger_count,
        "native_credit_accounts": native_count,
        "cross_catalog_matches": linked_count,
        "iceberg_snapshots": snapshots,
        "iceberg_data_files": files,
    }
    print("LAKEHOUSE_INTEROPERABILITY_PROOF=" + json.dumps(result, sort_keys=True))

    if min(ledger_count, native_count, linked_count, snapshots, files) < 1:
        raise RuntimeError(f"Catalog interoperability proof was incomplete: {result}")


if __name__ == "__main__":
    main()

