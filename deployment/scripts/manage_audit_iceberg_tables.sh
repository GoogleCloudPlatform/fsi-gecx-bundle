#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"

catalog_id="${AUDIT_ICEBERG_CATALOG_ID:-nova-audit-lakehouse}"
history_hours="${AUDIT_ICEBERG_HISTORY_HOURS:-6}"
retain_last="${AUDIT_ICEBERG_MIN_SNAPSHOTS:-60}"
bucket="gs://${PROJECT_ID}_audit-dataflow-staging"
script_uri="${bucket}/maintenance/manage_audit_iceberg_tables.py"
service_account="audit-iceberg-dataflow-sa@${PROJECT_ID}.iam.gserviceaccount.com"
batch_id="audit-table-maintenance-$(date -u +%Y%m%d-%H%M%S)"
rest_uri="https://biglake.googleapis.com/iceberg/v1/restcatalog"
submit_mode=()
if [[ "${ASYNC:-false}" == "true" ]]; then
  submit_mode+=(--async)
fi

gcloud storage cp deployment/spark/manage_audit_iceberg_tables.py "${script_uri}" \
  --project "${PROJECT_ID}"

properties="spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions"
properties+=",spark.sql.catalog.audit=org.apache.iceberg.spark.SparkCatalog"
properties+=",spark.sql.catalog.audit.type=rest"
properties+=",spark.sql.catalog.audit.uri=${rest_uri}"
properties+=",spark.sql.catalog.audit.warehouse=bl://projects/${PROJECT_ID}/catalogs/${catalog_id}"
properties+=",spark.sql.catalog.audit.header.x-goog-user-project=${PROJECT_ID}"
properties+=",spark.sql.catalog.audit.rest.auth.type=org.apache.iceberg.gcp.auth.GoogleAuthManager"
properties+=",spark.sql.catalog.audit.io-impl=org.apache.iceberg.gcp.gcs.GCSFileIO"
properties+=",spark.sql.catalog.audit.header.X-Iceberg-Access-Delegation=vended-credentials"

gcloud dataproc batches submit pyspark "${script_uri}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --batch "${batch_id}" \
  --version 2.3 \
  --service-account "${service_account}" \
  --subnet fsi-gecx-subnet \
  --properties "${properties}" \
  --deps-bucket "${PROJECT_ID}_audit-dataflow-staging" \
  "${submit_mode[@]}" \
  -- "--history-hours=${history_hours}" "--retain-last=${retain_last}"
