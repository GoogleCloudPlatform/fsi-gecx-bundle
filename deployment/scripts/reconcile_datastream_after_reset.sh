#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"

stream="banking-alloydb-cdc-stream"
dataset="iceberg_catalog"
action="${1:?Expected pause or rebuild}"

stream_state() {
  gcloud datastream streams describe "${stream}" \
    --project "${PROJECT_ID}" --location "${REGION}" --format='value(state)'
}

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

objects=()
while IFS= read -r object; do
  objects+=("${object}")
done < <(
  gcloud datastream objects list --stream="${stream}" \
    --project "${PROJECT_ID}" --location "${REGION}" --limit=10000 \
    --format='csv[no-heading](name.basename(),displayName)'
)
[[ "${#objects[@]}" -gt 0 ]] || {
  echo "No Datastream objects were found for ${stream}." >&2
  exit 1
}

for object in "${objects[@]}"; do
  object_id="${object%%,*}"
  source_name="${object#*,}"
  [[ "${source_name}" =~ ^[a-z0-9_]+\.[a-z0-9_]+$ ]] || {
    echo "Unsafe Datastream source object name: ${source_name}" >&2
    exit 1
  }
  table_name="${source_name/./_}"
  bq query --project_id="${PROJECT_ID}" --location=US --use_legacy_sql=false \
    "DROP TABLE IF EXISTS \`${PROJECT_ID}.${dataset}.${table_name}\`" >/dev/null
done

set_stream_state RUNNING

for object in "${objects[@]}"; do
  object_id="${object%%,*}"
  gcloud datastream objects start-backfill "${object_id}" \
    --stream="${stream}" --project "${PROJECT_ID}" --location "${REGION}" \
    --quiet >/dev/null
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
