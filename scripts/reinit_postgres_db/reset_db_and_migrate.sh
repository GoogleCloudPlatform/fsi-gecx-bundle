#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
: "${PROJECT_ID:?Set PROJECT_ID or configure the active gcloud project.}"

root="$(git rev-parse --show-toplevel)"
PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
  "${root}/deployment/scripts/reconcile_datastream_after_reset.sh" pause

for job in banking-db-bootstrap banking-db-migrate banking-db-reconcile banking-db-reset; do
  gcloud run jobs execute "${job}" --project "${PROJECT_ID}" --region "${REGION}" --wait
done

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
  "${root}/deployment/scripts/reconcile_alloydb_federation.sh"

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
  "${root}/deployment/scripts/reconcile_datastream_after_reset.sh" rebuild

gcloud run jobs execute lakehouse-view-reconcile \
  --project "${PROJECT_ID}" --region "${REGION}" --wait

echo "AlloyDB lifecycle, reset/seed, federation, CDC backfill, and curated views completed."
