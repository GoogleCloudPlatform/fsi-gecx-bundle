#!/usr/bin/env bash
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
