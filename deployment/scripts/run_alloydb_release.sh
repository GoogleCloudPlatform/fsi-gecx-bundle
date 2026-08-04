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
: "${RELEASE_COMMIT:?RELEASE_COMMIT is required}"
RELEASE_MODE="${RELEASE_MODE:-qualify}"
MANIFEST_URI="${MANIFEST_URI:-}"
: "${ROLLBACK_MANIFEST_URI:?ROLLBACK_MANIFEST_URI is required}"
ALLOW_CLOUD_SQL_CUTOVER="${ALLOW_CLOUD_SQL_CUTOVER:-false}"
cloud_sql_backup_id="${CLOUD_SQL_BACKUP_ID:-}"
source_metadata_path="/workspace/voice-release-source-metadata.json"
ces_release_result_path="/workspace/ces-release-result.json"
rollback_manifest_path="/workspace/rollback-release-manifest.json"
rollback_target_path="/workspace/rollback-target.json"

declare -A images
components=(banking-service banking-ui credit-support-agent data-generator)

resolve_image() {
  local component="$1"
  local repository="${REGION}-docker.pkg.dev/${PROJECT_ID}/fsi-gecx-bundle/${component}"
  local digest
  digest="$(gcloud artifacts docker images describe "${repository}:${RELEASE_COMMIT}" --format='value(image_summary.digest)' 2>/dev/null || true)"
  if [[ "${digest}" =~ ^sha256:[a-f0-9]{64}$ ]]; then
    printf '%s@%s' "${repository}" "${digest}"
    return
  fi
  echo "No image tagged with exact release commit for ${component}: ${RELEASE_COMMIT}" >&2
  exit 1
}

if [[ "${RELEASE_MODE}" == "promote" ]]; then
  : "${MANIFEST_URI:?MANIFEST_URI is required for promotion}"
  gsutil cp "${MANIFEST_URI}" /workspace/source-release-manifest.json
  [[ "$(jq -r .status /workspace/source-release-manifest.json)" == "qualified" ]]
  [[ "$(jq -r .commit /workspace/source-release-manifest.json)" == "${RELEASE_COMMIT}" ]]
  python3 deployment/scripts/voice_release_metadata.py validate \
    --root /workspace \
    --manifest /workspace/source-release-manifest.json \
    --commit "${RELEASE_COMMIT}"
  for component in "${components[@]}"; do
    images["${component}"]="$(jq -er --arg component "${component}" '.images[$component]' /workspace/source-release-manifest.json)"
  done
else
  for component in "${components[@]}"; do
    images["${component}"]="$(resolve_image "${component}")"
  done
fi

gsutil cp "${ROLLBACK_MANIFEST_URI}" "${rollback_manifest_path}"
python3 deployment/scripts/voice_release_metadata.py rollback-target \
  --manifest "${rollback_manifest_path}" \
  --environment "${PROJECT_ID}" \
  --manifest-uri "${ROLLBACK_MANIFEST_URI}" \
  > "${rollback_target_path}"
while IFS= read -r rollback_image; do
  gcloud artifacts docker images describe "${rollback_image}" >/dev/null
done < <(jq -er '.images[]' "${rollback_target_path}")

python3 deployment/scripts/voice_release_metadata.py inspect --root /workspace \
  > "${source_metadata_path}"
EXPECTED_ALEMBIC_REVISION="$(
  jq -er '
    .database.alembic_heads
    | if length == 1 then .[0] else error("release requires one Alembic head") end
  ' "${source_metadata_path}"
)"

for component in "${components[@]}"; do
  [[ "${images[$component]}" =~ @sha256:[a-f0-9]{64}$ ]] || { echo "Mutable or invalid image for ${component}" >&2; exit 1; }
  gcloud artifacts docker images describe "${images[$component]}" >/dev/null
done

terraform -chdir=deployment/terraform init -reconfigure -input=false \
  -backend-config="environment/${PROJECT_ID}/gcs.tfbackend"
if terraform -chdir=deployment/terraform state list | grep -q '^google_sql_database_instance\.banking_data$'; then
  [[ "${ALLOW_CLOUD_SQL_CUTOVER}" == "true" ]] || {
    echo "Legacy Cloud SQL is still managed. Re-run this approved destructive release with ALLOW_CLOUD_SQL_CUTOVER=true." >&2
    exit 1
  }
  gcloud sql backups create --project "${PROJECT_ID}" --instance banking-data \
    --description "Final pre-AlloyDB backup for ${RELEASE_COMMIT}" --quiet
  cloud_sql_backup_id="$(gcloud sql backups list --project "${PROJECT_ID}" --instance banking-data --limit 1 --sort-by='~startTime' --format='value(id)')"
  mapfile -t legacy_sql_state < <(terraform -chdir=deployment/terraform state list | grep '^google_sql_')
  terraform -chdir=deployment/terraform state rm "${legacy_sql_state[@]}"
  gcloud sql instances patch banking-data --project "${PROJECT_ID}" \
    --no-deletion-protection --retain-backups-on-delete --quiet
  gcloud sql instances delete banking-data --project "${PROJECT_ID}" \
    --enable-final-backup --final-backup-retention-days=30 \
    --final-backup-description="Final AlloyDB cutover backup for ${RELEASE_COMMIT}" --quiet
fi
terraform -chdir=deployment/terraform plan -input=false \
  -var-file="environment/${PROJECT_ID}/terraform.tfvars" -out=/workspace/release.tfplan

# Datastream destination changes require a paused stream. Detect any planned
# mutation of the existing stream before apply; fresh environments have no
# prior stream and do not need this step. The normal post-reset rebuild below
# resumes the stream and proves every object backfill.
if terraform -chdir=deployment/terraform show -json /workspace/release.tfplan | jq -e '
  .resource_changes[]?
  | select(.address == "google_datastream_stream.banking_cdc_stream")
  | select(.change.before != null)
  | select(.change.actions != ["no-op"])
' >/dev/null; then
  PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
    deployment/scripts/reconcile_datastream_after_reset.sh pause
fi
terraform -chdir=deployment/terraform apply -input=false -auto-approve /workspace/release.tfplan

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" deployment/scripts/reconcile_alloydb_iam_groups.sh

banking_image="${images[banking-service]}"
gcloud run jobs update banking-db-bootstrap --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run jobs update banking-db-migrate --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run jobs update banking-db-reconcile --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run jobs update banking-db-reset --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run jobs update banking-knowledge-catalog-sync --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run jobs update audit-outbox-relay --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run jobs update audit-iceberg-bootstrap --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet

gcloud run jobs execute banking-db-bootstrap --project "${PROJECT_ID}" --region "${REGION}" --wait
gcloud run jobs execute banking-db-migrate --project "${PROJECT_ID}" --region "${REGION}" --wait
gcloud run jobs execute banking-db-reconcile --project "${PROJECT_ID}" --region "${REGION}" --wait
gcloud run jobs execute audit-iceberg-bootstrap --project "${PROJECT_ID}" --region "${REGION}" --wait

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" RELEASE_COMMIT="${RELEASE_COMMIT}" \
  deployment/scripts/deploy_audit_iceberg_pipeline.sh

gcloud run services update banking-service --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run services update banking-ui --project "${PROJECT_ID}" --region "${REGION}" --image "${images[banking-ui]}" --quiet
gcloud run services update credit-support-agent --project "${PROJECT_ID}" --region "${REGION}" --image "${images[credit-support-agent]}" --quiet
gcloud run services update data-generator --project "${PROJECT_ID}" --region "${REGION}" --image "${images[data-generator]}" --quiet
PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" deployment/scripts/reconcile_datastream_after_reset.sh pause
gcloud run jobs execute banking-db-reset --project "${PROJECT_ID}" --region "${REGION}" --wait
runtime_validation_started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
gcloud run jobs execute banking-knowledge-catalog-sync --project "${PROJECT_ID}" --region "${REGION}" --wait

gecx_deployment="$(
  terraform -chdir=deployment/terraform output -raw \
    cx_agent_studio_voice_agent_deployment_name
)"
gecx_location="$(terraform -chdir=deployment/terraform output -raw gecx_location)"
gecx_app_id="$(printf '%s' "${gecx_deployment}" | awk -F/ '{print $6}')"
[[ -n "${gecx_app_id}" ]] || {
  echo "Could not derive CES app ID from ${gecx_deployment}" >&2
  exit 1
}
PROJECT_ID="${PROJECT_ID}" \
  LOCATION="${gecx_location}" \
  APP_ID="${gecx_app_id}" \
  AGENT_FOLDER="Credit_Support_Voice_Agent" \
  TARGET_DEPLOYMENT_NAME="${gecx_deployment}" \
  RESULT_FILE="${ces_release_result_path}" \
  scripts/cxas/overwrite_cxas_agent.sh

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" deployment/scripts/reconcile_alloydb_federation.sh
PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" deployment/scripts/reconcile_datastream_after_reset.sh rebuild
gcloud run jobs execute lakehouse-view-reconcile --project "${PROJECT_ID}" --region "${REGION}" --wait

banking_url="$(gcloud run services describe banking-service --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
ui_url="$(gcloud run services describe banking-ui --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
voice_url="$(gcloud run services describe credit-support-agent --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
generator_url="$(gcloud run services describe data-generator --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
release_runner="cloudbuild-terraform-sa@${PROJECT_ID}.iam.gserviceaccount.com"
identity_token() {
  gcloud auth print-identity-token \
    --impersonate-service-account="${release_runner}" \
    --audiences="$1"
}
curl --fail --silent --show-error -H "Authorization: Bearer $(identity_token "${banking_url}")" "${banking_url}/health" >/dev/null
curl --fail --silent --show-error -H "Authorization: Bearer $(identity_token "${ui_url}")" "${ui_url}/" >/dev/null
curl --fail --silent --show-error -H "Authorization: Bearer $(identity_token "${voice_url}")" "${voice_url}/" >/dev/null
curl --fail --silent --show-error -H "Authorization: Bearer $(identity_token "${generator_url}")" "${generator_url}/health" >/dev/null

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
  VALIDATION_START_TIME="${runtime_validation_started_at}" \
  deployment/scripts/validate_audit_iceberg_runtime.sh

manifest_path="/workspace/release-manifest-${RELEASE_COMMIT}.json"
jq -n \
  --arg commit "${RELEASE_COMMIT}" \
  --arg environment "${PROJECT_ID}" \
  --arg mode "${RELEASE_MODE}" \
  --arg alembic "${EXPECTED_ALEMBIC_REVISION}" \
  --arg banking "${images[banking-service]}" \
  --arg ui "${images[banking-ui]}" \
  --arg voice "${images[credit-support-agent]}" \
  --arg generator "${images[data-generator]}" \
  --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg cloud_sql_backup_id "${cloud_sql_backup_id}" \
  --slurpfile source_metadata "${source_metadata_path}" \
  --slurpfile ces_result "${ces_release_result_path}" \
  --slurpfile rollback_target "${rollback_target_path}" \
  '{
    schema_version:3,
    status:(if $mode=="promote" then "promoted" else "qualified" end),
    mode:$mode,
    commit:$commit,
    environment:$environment,
    alembic_revision:$alembic,
    database:$source_metadata[0].database,
    images:{
      "banking-service":$banking,
      "banking-ui":$ui,
      "credit-support-agent":$voice,
      "data-generator":$generator
    },
    ces:{
      app:$ces_result[0].app,
      version:$ces_result[0].version,
      deployment:$ces_result[0].deployments[0],
      config_sha256:$source_metadata[0].ces_config.sha256,
      model:$source_metadata[0].ces_config.model
    },
    knowledge_catalog:$source_metadata[0].knowledge_catalog,
    rollback_target:$rollback_target[0],
    data_platform:{
      oltp_cdc_dataset:"oltp_cdc",
      curated_dataset:"analytics_curated",
      audit_dataset:"compliance_audit"
    },
    cutover:{
      final_cloud_sql_backup_id:
        (if $cloud_sql_backup_id=="" then null else $cloud_sql_backup_id end)
    },
    validation:{
      terraform:true,
      bootstrap:true,
      migration:true,
      reconciliation:true,
      reset_seed:true,
      knowledge_catalog:true,
      ces_deployment:true,
      datastream:true,
      federation:true,
      audit_iceberg_dataflow:true,
      audit_iceberg_runtime:true,
      spark_interoperability:true,
      service_health:true
    },
    completed_at:$timestamp
  }' \
  > "${manifest_path}"
destination="gs://${PROJECT_ID}-fsi-release-manifests/alloydb/${RELEASE_COMMIT}/${RELEASE_MODE}.json"
gsutil cp "${manifest_path}" "${destination}"
echo "Release manifest: ${destination}"
