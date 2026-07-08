#!/usr/bin/env bash

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
SOURCE_DATASET="${SOURCE_DATASET:-iceberg_catalog}"
CURATED_DATASET="${CURATED_DATASET:-analytics_curated}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
POLL_SECONDS="${POLL_SECONDS:-10}"

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
ROOT_DIR=$(dirname "$(dirname "$SCRIPT_DIR")")
VIEW_DIR="${ROOT_DIR}/deployment/bigquery/${CURATED_DATASET}/view"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "PROJECT_ID is required to bootstrap curated BigQuery views." >&2
  exit 1
fi

required_tables=(
  "cards_transaction_authorization"
  "cards_posted_transactions"
  "cards_issued_card"
)

deadline=$((SECONDS + TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  present_count="$(
    bq query --project_id="${PROJECT_ID}" --use_legacy_sql=false --format=csv \
      "SELECT table_name
       FROM \`${PROJECT_ID}.${SOURCE_DATASET}.INFORMATION_SCHEMA.TABLES\`
       WHERE table_name IN ('cards_transaction_authorization', 'cards_posted_transactions', 'cards_issued_card')" \
      | tail -n +2 | sed '/^$/d' | wc -l | tr -d ' '
  )"

  if [[ "${present_count}" == "${#required_tables[@]}" ]]; then
    break
  fi

  echo "Waiting for Datastream tables in ${PROJECT_ID}.${SOURCE_DATASET} (${present_count}/${#required_tables[@]} present)..."
  sleep "${POLL_SECONDS}"
done

if [[ "${present_count}" != "${#required_tables[@]}" ]]; then
  echo "Timed out waiting for Datastream tables in ${PROJECT_ID}.${SOURCE_DATASET}." >&2
  exit 1
fi

for sql_file in "${VIEW_DIR}"/*.sql; do
  echo "Applying curated view from ${sql_file##*/}..."
  sed "s/__PROJECT_ID__/${PROJECT_ID}/g" "${sql_file}" \
    | bq query --project_id="${PROJECT_ID}" --use_legacy_sql=false
done

echo "Curated BigQuery views are ready in ${PROJECT_ID}.${CURATED_DATASET}."
