#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"

connection_id="banking-postgres-connection"
location="US"
connector_user="banking_bq_connector"
password="$(gcloud secrets versions access latest --project "${PROJECT_ID}" --secret postgres_banking_bq_connector_password)"
resource_uri="//alloydb.googleapis.com/projects/${PROJECT_ID}/locations/${REGION}/clusters/banking-data/instances/banking-primary"

existing_connector="$(bq show --format=prettyjson --connection "${PROJECT_ID}.${location}.${connection_id}" 2>/dev/null | jq -r '.connectorConfiguration.connectorId // empty' || true)"
if [[ "${existing_connector}" != "google-alloydb" ]]; then
  if [[ -n "${existing_connector}" ]] || bq show --connection "${PROJECT_ID}.${location}.${connection_id}" >/dev/null 2>&1; then
    bq rm -f --connection "${PROJECT_ID}.${location}.${connection_id}"
  fi
  connector_configuration="$(jq -cn \
    --arg database banking \
    --arg resource "${resource_uri}" \
    --arg username "${connector_user}" \
    --arg password "${password}" \
    '{connector_id:"google-alloydb",asset:{database:$database,google_cloud_resource:$resource},authentication:{username_password:{username:$username,password:{plaintext:$password}}}}')"
  bq mk --connection --location="${location}" --project_id="${PROJECT_ID}" \
    --connector_configuration "${connector_configuration}" "${connection_id}"
fi
unset password connector_configuration

project_number="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:service-${project_number}@gcp-sa-bigqueryconnection.iam.gserviceaccount.com" \
  --role=roles/alloydb.client --quiet >/dev/null

bq query --project_id="${PROJECT_ID}" --location="${location}" --use_legacy_sql=false \
  "SELECT 1 AS federation_ok FROM EXTERNAL_QUERY('${PROJECT_ID}.${location}.${connection_id}', 'SELECT 1')"
