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

connection_id="banking-postgres-connection"
location="US"
connector_user="banking_bq_connector"
password="$(gcloud secrets versions access latest --project "${PROJECT_ID}" --secret postgres_banking_bq_connector_password)"
resource_uri="//alloydb.googleapis.com/projects/${PROJECT_ID}/locations/${REGION}/clusters/banking-data/instances/banking-primary"

existing_connector="$(bq show --format=json --connection "${PROJECT_ID}.${location}.${connection_id}" 2>/dev/null | jq -r '.configuration.connectorId // empty' || true)"
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
  --role=roles/alloydb.client --condition=None --quiet >/dev/null

bq query --project_id="${PROJECT_ID}" --location="${location}" --use_legacy_sql=false \
  "SELECT 1 AS federation_ok FROM EXTERNAL_QUERY('${PROJECT_ID}.${location}.${connection_id}', 'SELECT 1')"
