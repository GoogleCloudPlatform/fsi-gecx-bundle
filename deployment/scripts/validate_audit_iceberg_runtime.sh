#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"
: "${VALIDATION_START_TIME:?VALIDATION_START_TIME is required (RFC3339 UTC)}"

job_name="${AUDIT_ICEBERG_JOB_NAME:-nova-audit-iceberg}"
relay_job="${AUDIT_OUTBOX_RELAY_JOB_NAME:-audit-outbox-relay}"
main_subscription="${AUDIT_ICEBERG_SUBSCRIPTION:-audit-events-iceberg-sub}"
dlq_subscription="${AUDIT_ICEBERG_DLQ_SUBSCRIPTION:-audit-events-iceberg-dlq-sub}"
timeout_seconds="${AUDIT_ICEBERG_VALIDATION_TIMEOUT_SECONDS:-900}"
run_spark="${RUN_SPARK_INTEROPERABILITY:-true}"
deadline=$((SECONDS + timeout_seconds))

retry_until() {
  local description="$1"
  shift
  until "$@"; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for ${description}." >&2
      return 1
    fi
    sleep 10
  done
}

running_jobs="$(
  gcloud dataflow jobs list \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --filter "name=${job_name} AND state=Running" \
    --format='value(id)'
)"
running_job_count="$(awk 'NF {count++} END {print count+0}' <<<"${running_jobs}")"
if [[ "${running_job_count}" -ne 1 ]]; then
  echo "Expected exactly one running ${job_name} Dataflow job; found ${running_job_count}." >&2
  exit 1
fi
dataflow_job_id="$(awk 'NF {print; exit}' <<<"${running_jobs}")"

latest_relay_event_id=""
find_post_reset_relay_event() {
  local result
  result="$(gcloud logging read \
    "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${relay_job}\" AND logName=\"projects/${PROJECT_ID}/logs/run.googleapis.com%2Fstdout\" AND timestamp>=\"${VALIDATION_START_TIME}\" AND jsonPayload.status=\"ok\" AND jsonPayload.published>0" \
    --project "${PROJECT_ID}" \
    --order desc \
    --limit 1 \
    --format=json)"
  latest_relay_event_id="$(jq -r '.[0].jsonPayload.last_event_id // empty' <<<"${result}")"
  [[ "${latest_relay_event_id}" =~ ^[A-Za-z0-9_-]+$ ]]
}

# Trigger one bounded relay pass instead of relying only on scheduler timing.
gcloud run jobs execute "${relay_job}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --wait >/dev/null || true
retry_until "a post-reset outbox relay batch" find_post_reset_relay_event

event_visible_in_iceberg() {
  local result
  result="$(bq query \
    --project_id="${PROJECT_ID}" \
    --use_legacy_sql=false \
    --format=prettyjson \
    "SELECT COUNT(*) AS matched FROM \`${PROJECT_ID}.compliance_audit.audit_events\` WHERE event_id = '${latest_relay_event_id}'")"
  [[ "$(jq -r '.[0].matched // "0"' <<<"${result}")" -ge 1 ]]
}
retry_until "relay event ${latest_relay_event_id} in logical Iceberg audit history" event_visible_in_iceberg

integrity="$(bq query \
  --project_id="${PROJECT_ID}" \
  --use_legacy_sql=false \
  --format=prettyjson \
  "SELECT
     (SELECT COUNT(*) FROM \`${PROJECT_ID}.compliance_audit.audit_events\`) AS audit_events,
     (SELECT COUNT(DISTINCT event_id) FROM \`${PROJECT_ID}.compliance_audit.audit_events\`) AS distinct_audit_events,
     (SELECT COUNT(*) FROM \`${PROJECT_ID}.compliance_audit.account_ledger_entries\`) AS ledger_entries,
     (SELECT COUNT(DISTINCT entry_id) FROM \`${PROJECT_ID}.compliance_audit.account_ledger_entries\`) AS distinct_ledger_entries,
     (SELECT COUNT(*) FROM \`${PROJECT_ID}.compliance_audit.account_ledger_balance\` WHERE imbalance_cents != 0) AS imbalanced_transactions")"

audit_events="$(jq -r '.[0].audit_events | tonumber' <<<"${integrity}")"
distinct_audit_events="$(jq -r '.[0].distinct_audit_events | tonumber' <<<"${integrity}")"
ledger_entries="$(jq -r '.[0].ledger_entries | tonumber' <<<"${integrity}")"
distinct_ledger_entries="$(jq -r '.[0].distinct_ledger_entries | tonumber' <<<"${integrity}")"
imbalanced_transactions="$(jq -r '.[0].imbalanced_transactions | tonumber' <<<"${integrity}")"

(( audit_events > 0 && ledger_entries > 0 ))
[[ "${audit_events}" -eq "${distinct_audit_events}" ]]
[[ "${ledger_entries}" -eq "${distinct_ledger_entries}" ]]
[[ "${imbalanced_transactions}" -eq 0 ]]

dataflow_errors="$(gcloud logging read \
  "resource.type=\"dataflow_step\" AND resource.labels.job_id=\"${dataflow_job_id}\" AND timestamp>=\"${VALIDATION_START_TIME}\" AND severity>=ERROR" \
  --project "${PROJECT_ID}" \
  --limit 1 \
  --format='value(insertId)')"
[[ -z "${dataflow_errors}" ]]

subscription_backlog() {
  local subscription="$1"
  local access_token end response
  access_token="$(gcloud auth print-access-token)"
  end="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  response="$(curl --fail --silent --show-error -G \
    -H "Authorization: Bearer ${access_token}" \
    "https://monitoring.googleapis.com/v3/projects/${PROJECT_ID}/timeSeries" \
    --data-urlencode "filter=metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" AND resource.type=\"pubsub_subscription\" AND resource.label.subscription_id=\"${subscription}\"" \
    --data-urlencode "interval.startTime=${VALIDATION_START_TIME}" \
    --data-urlencode "interval.endTime=${end}" \
    --data-urlencode 'view=FULL')"
  jq -er '[.timeSeries[].points[]] | max_by(.interval.endTime) | (.value.int64Value // "0") | tonumber' <<<"${response}"
}

subscriptions_drained() {
  local main_backlog dlq_backlog
  main_backlog="$(subscription_backlog "${main_subscription}" 2>/dev/null)" || return 1
  dlq_backlog="$(subscription_backlog "${dlq_subscription}" 2>/dev/null)" || return 1
  [[ "${main_backlog}" -eq 0 && "${dlq_backlog}" -eq 0 ]]
}
retry_until "primary and DLQ Pub/Sub subscriptions to drain" subscriptions_drained

case "${run_spark}" in
  1|true|TRUE|yes|YES|on|ON)
    PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
      deployment/scripts/validate_lakehouse_interoperability.sh
    ;;
esac

jq -n \
  --arg dataflow_job_id "${dataflow_job_id}" \
  --arg relay_event_id "${latest_relay_event_id}" \
  --argjson audit_events "${audit_events}" \
  --argjson ledger_entries "${ledger_entries}" \
  '{status:"ok",dataflow_job_id:$dataflow_job_id,relay_event_id:$relay_event_id,audit_events:$audit_events,ledger_entries:$ledger_entries,duplicates:0,imbalanced_transactions:0,subscription_backlog:0,dlq_backlog:0}'
