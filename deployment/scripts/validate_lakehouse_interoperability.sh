#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"

catalog_id="${AUDIT_ICEBERG_CATALOG_ID:-nova-audit-lakehouse}"
bucket="gs://${PROJECT_ID}_audit-dataflow-staging"
script_uri="${bucket}/validation/validate_catalog_interoperability.py"
service_account="audit-iceberg-dataflow-sa@${PROJECT_ID}.iam.gserviceaccount.com"
batch_id="audit-catalog-proof-$(date -u +%Y%m%d-%H%M%S)"
rest_uri="https://biglake.googleapis.com/iceberg/v1/restcatalog"

gcloud storage cp deployment/spark/validate_catalog_interoperability.py "${script_uri}" \
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
  -- "--project-id=${PROJECT_ID}"
