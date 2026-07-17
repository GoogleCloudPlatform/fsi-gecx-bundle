#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"
: "${RELEASE_COMMIT:?RELEASE_COMMIT is required}"

catalog_id="${AUDIT_ICEBERG_CATALOG_ID:-nova-audit-lakehouse}"
job_name="${AUDIT_ICEBERG_JOB_NAME:-nova-audit-iceberg}"
commit_frequency="${AUDIT_ICEBERG_COMMIT_FREQUENCY_SECONDS:-60}"
repository="${REGION}-docker.pkg.dev/${PROJECT_ID}/fsi-gecx-bundle"
image="${repository}/audit-iceberg-dataflow:${RELEASE_COMMIT}"
staging_bucket="gs://${PROJECT_ID}_audit-dataflow-staging"
template_uri="${staging_bucket}/templates/audit-iceberg.json"
service_account="audit-iceberg-dataflow-sa@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud builds submit deployment/dataflow-audit-iceberg \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --config deployment/dataflow-audit-iceberg/cloudbuild.yaml \
  --substitutions "_IMAGE=${image}" \
  --quiet

run_args=(
  dataflow flex-template run "${job_name}"
  --project "${PROJECT_ID}"
  --region "${REGION}"
  --template-file-gcs-location "${template_uri}"
  --service-account-email "${service_account}"
  --subnetwork "https://www.googleapis.com/compute/v1/projects/${PROJECT_ID}/regions/${REGION}/subnetworks/fsi-gecx-subnet"
  --disable-public-ips
  --enable-streaming-engine
  --num-workers 1
  --max-workers 3
  --staging-location "${staging_bucket}/staging"
  --temp-location "${staging_bucket}/temp"
  --additional-user-labels "component=audit-iceberg,release=${RELEASE_COMMIT:0:12}"
  --parameters "inputSubscription=projects/${PROJECT_ID}/subscriptions/audit-events-iceberg-sub,dlqTopic=projects/${PROJECT_ID}/topics/audit-events-iceberg-dlq,warehouse=bl://projects/${PROJECT_ID}/catalogs/${catalog_id},commitFrequencySeconds=${commit_frequency}"
)

running_job="$(gcloud dataflow jobs list \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --status active \
  --filter "name=${job_name}" \
  --format 'value(name)' \
  --limit 1)"
if [[ -n "${running_job}" ]]; then
  run_args+=(--update)
fi

gcloud "${run_args[@]}"

