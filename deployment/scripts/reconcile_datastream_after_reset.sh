#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"

stream="${DATASTREAM_STREAM_ID:-banking-alloydb-oltp-cdc-stream}"
legacy_stream="banking-alloydb-cdc-stream"
dataset="oltp_cdc"
action="${1:?Expected pause or rebuild}"
expected_objects=(
  catalog.credit_products
  catalog.deposit_products
  cards.posted_transactions
  cards.credit_accounts
  cards.issued_card
  cards.transaction_authorization
  origination.applications
  origination.credit_card_applications
  origination.mortgage_applications
  origination.deposit_applications
  origination.application_artifacts
  identity.users
  identity.user_addresses
  identity.user_devices
  identity.user_secure_messages
  kyc.user_credit_profiles
  ledger.accounts
  ledger.transactions
  ledger.account_ledger
  merchants.merchant_master
  merchants.merchant_stores
  merchants.merchant_category_codes
  operations.fraud_model_decisions
  operations.fraud_alerts
  operations.fraud_case_actions
  operations.scenario_outcomes
  operations.support_escalations
  operations.retail_locations
)

stream_state() {
  gcloud datastream streams describe "${stream}" \
    --project "${PROJECT_ID}" --location "${REGION}" --format='value(state)'
}

# During the one-time dataset rename, Terraform must replace the stream because
# the Datastream API does not allow changing its destination dataset in place.
# Pause the legacy stream before that replacement; rebuilds must always target
# the new stream so data cannot accidentally flow back into the old dataset.
if [[ "${action}" == "pause" ]] && ! gcloud datastream streams describe "${stream}" \
  --project "${PROJECT_ID}" --location "${REGION}" >/dev/null 2>&1; then
  if gcloud datastream streams describe "${legacy_stream}" \
    --project "${PROJECT_ID}" --location "${REGION}" >/dev/null 2>&1; then
    stream="${legacy_stream}"
  fi
fi

wait_for_stream_state() {
  local expected="$1"
  local actual=""
  for _ in $(seq 1 90); do
    actual="$(stream_state)"
    [[ "${actual}" == "${expected}" ]] && return
    sleep 10
  done
  gcloud datastream streams describe "${stream}" \
    --project "${PROJECT_ID}" --location "${REGION}" \
    --format='yaml(state,errors)' >&2
  echo "Datastream did not reach ${expected}; last state was ${actual}." >&2
  exit 1
}

set_stream_state() {
  local state="$1"
  gcloud datastream streams update "${stream}" \
    --project "${PROJECT_ID}" --location "${REGION}" \
    --state="${state}" --update-mask=state --quiet >/dev/null
  wait_for_stream_state "${state}"
}

if [[ "${action}" == "pause" ]]; then
  current_state="$(stream_state)"
  if [[ "${current_state}" == "PAUSED" || "${current_state}" == "NOT_STARTED" ]]; then
    exit 0
  fi
  set_stream_state PAUSED
  exit 0
fi

[[ "${action}" == "rebuild" ]] || {
  echo "Expected pause or rebuild, received ${action}." >&2
  exit 2
}

for source_name in "${expected_objects[@]}"; do
  table_name="${source_name/./_}"
  bq query --project_id="${PROJECT_ID}" --location=US --use_legacy_sql=false \
    "DROP TABLE IF EXISTS \`${PROJECT_ID}.${dataset}.${table_name}\`" >/dev/null
done

set_stream_state RUNNING

# A never-started stream does not expose its object resources. Wait until the
# first start discovers the complete include list before managing backfills.
objects=()
for _ in $(seq 1 90); do
  objects=()
  while IFS= read -r object; do
    [[ -n "${object}" ]] && objects+=("${object}")
  done < <(
    gcloud datastream objects list --stream="${stream}" \
      --project "${PROJECT_ID}" --location "${REGION}" --limit=10000 \
      --format='csv[no-heading](name.basename(),displayName)'
  )
  [[ "${#objects[@]}" == "${#expected_objects[@]}" ]] && break
  sleep 10
done
[[ "${#objects[@]}" == "${#expected_objects[@]}" ]] || {
  echo "Expected ${#expected_objects[@]} Datastream objects, found ${#objects[@]}." >&2
  exit 1
}

declare -A discovered=()
for object in "${objects[@]}"; do
  source_name="${object#*,}"
  [[ "${source_name}" =~ ^[a-z0-9_]+\.[a-z0-9_]+$ ]] || {
    echo "Unsafe Datastream source object name: ${source_name}" >&2
    exit 1
  }
  discovered["${source_name}"]=1
done
for source_name in "${expected_objects[@]}"; do
  [[ -n "${discovered[$source_name]:-}" ]] || {
    echo "Expected Datastream object was not discovered: ${source_name}" >&2
    exit 1
  }
done

for object in "${objects[@]}"; do
  object_id="${object%%,*}"
  object_json="$(gcloud datastream objects describe "${object_id}" \
    --stream="${stream}" --project "${PROJECT_ID}" \
    --location "${REGION}" --format=json)"
  backfill_state="$(jq -r '.backfillJob.state // "PENDING"' <<<"${object_json}")"
  # A fresh stream starts its configured automatic backfill itself. A resumed
  # stream has COMPLETED object jobs from the prior snapshot and needs an
  # explicit replacement backfill after its destination tables are dropped.
  if [[ "${backfill_state}" == "COMPLETED" ]]; then
    gcloud datastream objects start-backfill "${object_id}" \
      --stream="${stream}" --project "${PROJECT_ID}" --location "${REGION}" \
      --quiet >/dev/null
  fi
done

for _ in $(seq 1 90); do
  pending=0
  for object in "${objects[@]}"; do
    object_id="${object%%,*}"
    object_json="$(gcloud datastream objects describe "${object_id}" \
      --stream="${stream}" --project "${PROJECT_ID}" \
      --location "${REGION}" --format=json)"
    backfill_state="$(jq -r '.backfillJob.state // "PENDING"' <<<"${object_json}")"
    if [[ "${backfill_state}" == "FAILED" ]]; then
      jq '{displayName, backfillJob}' <<<"${object_json}" >&2
      exit 1
    fi
    [[ "${backfill_state}" == "COMPLETED" ]] || pending=$((pending + 1))
  done
  [[ "${pending}" == "0" ]] && exit 0
  sleep 10
done

echo "Datastream backfills did not complete before the release timeout." >&2
exit 1
