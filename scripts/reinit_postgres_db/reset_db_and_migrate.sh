#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
: "${PROJECT_ID:?Set PROJECT_ID or configure the active gcloud project.}"

gcloud datastream streams update banking-cdc-stream \
  --project "${PROJECT_ID}" --location "${REGION}" \
  --state=PAUSED --update-mask=state --quiet

for job in banking-db-bootstrap banking-db-migrate banking-db-reconcile banking-db-reset; do
  gcloud run jobs execute "${job}" --project "${PROJECT_ID}" --region "${REGION}" --wait
done

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
  "$(git rev-parse --show-toplevel)/deployment/scripts/reconcile_alloydb_federation.sh"

gcloud datastream streams update banking-cdc-stream \
  --project "${PROJECT_ID}" --location "${REGION}" \
  --state=RUNNING --update-mask=state --quiet

echo "AlloyDB lifecycle, reset/seed, federation, and CDC activation completed."
