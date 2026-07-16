#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${REGION:?REGION is required}"
: "${RELEASE_COMMIT:?RELEASE_COMMIT is required}"
RELEASE_MODE="${RELEASE_MODE:-qualify}"
MANIFEST_URI="${MANIFEST_URI:-}"
ALLOW_CLOUD_SQL_CUTOVER="${ALLOW_CLOUD_SQL_CUTOVER:-false}"
EXPECTED_ALEMBIC_REVISION="2ea57c78ba89"
cloud_sql_backup_id=""

declare -A images
components=(banking-service credit-support-agent data-generator)

resolve_image() {
  local component="$1"
  local repository="${REGION}-docker.pkg.dev/${PROJECT_ID}/fsi-gecx-bundle/${component}"
  local digest
  digest="$(gcloud artifacts docker images describe "${repository}:${RELEASE_COMMIT}" --format='value(image_summary.digest)' 2>/dev/null || true)"
  if [[ "${digest}" =~ ^sha256:[a-f0-9]{64}$ ]]; then
    printf '%s@%s' "${repository}" "${digest}"
    return
  fi
  current="$(gcloud run services describe "${component}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true)"
  [[ "${current}" =~ @sha256:[a-f0-9]{64}$ ]] || { echo "No immutable image available for ${component}" >&2; exit 1; }
  printf '%s' "${current}"
}

if [[ "${RELEASE_MODE}" == "promote" ]]; then
  : "${MANIFEST_URI:?MANIFEST_URI is required for promotion}"
  gsutil cp "${MANIFEST_URI}" /workspace/source-release-manifest.json
  [[ "$(jq -r .status /workspace/source-release-manifest.json)" == "qualified" ]]
  [[ "$(jq -r .commit /workspace/source-release-manifest.json)" == "${RELEASE_COMMIT}" ]]
  for component in "${components[@]}"; do
    images["${component}"]="$(jq -er --arg component "${component}" '.images[$component]' /workspace/source-release-manifest.json)"
  done
else
  for component in "${components[@]}"; do
    images["${component}"]="$(resolve_image "${component}")"
  done
fi

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
terraform -chdir=deployment/terraform apply -input=false -auto-approve /workspace/release.tfplan

banking_image="${images[banking-service]}"
gcloud run jobs update banking-db-bootstrap --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run jobs update banking-db-migrate --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run jobs update banking-db-reconcile --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run jobs update banking-db-reset --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet

gcloud run jobs execute banking-db-bootstrap --project "${PROJECT_ID}" --region "${REGION}" --wait
gcloud run jobs execute banking-db-migrate --project "${PROJECT_ID}" --region "${REGION}" --wait
gcloud run jobs execute banking-db-reconcile --project "${PROJECT_ID}" --region "${REGION}" --wait

gcloud run services update banking-service --project "${PROJECT_ID}" --region "${REGION}" --image "${banking_image}" --quiet
gcloud run services update credit-support-agent --project "${PROJECT_ID}" --region "${REGION}" --image "${images[credit-support-agent]}" --quiet
gcloud run services update data-generator --project "${PROJECT_ID}" --region "${REGION}" --image "${images[data-generator]}" --quiet
gcloud run jobs execute banking-db-reset --project "${PROJECT_ID}" --region "${REGION}" --wait

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" deployment/scripts/reconcile_alloydb_federation.sh
gcloud datastream streams update banking-cdc-stream --project "${PROJECT_ID}" --location "${REGION}" --state=RUNNING --update-mask=state --quiet

identity_token="$(gcloud auth print-identity-token)"
banking_url="$(gcloud run services describe banking-service --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
voice_url="$(gcloud run services describe credit-support-agent --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
generator_url="$(gcloud run services describe data-generator --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')"
curl --fail --silent --show-error -H "Authorization: Bearer ${identity_token}" "${banking_url}/api/health" >/dev/null
curl --fail --silent --show-error -H "Authorization: Bearer ${identity_token}" "${voice_url}/healthz" >/dev/null
curl --fail --silent --show-error -H "Authorization: Bearer ${identity_token}" "${generator_url}/health" >/dev/null

manifest_path="/workspace/release-manifest-${RELEASE_COMMIT}.json"
jq -n \
  --arg commit "${RELEASE_COMMIT}" \
  --arg environment "${PROJECT_ID}" \
  --arg mode "${RELEASE_MODE}" \
  --arg alembic "${EXPECTED_ALEMBIC_REVISION}" \
  --arg banking "${images[banking-service]}" \
  --arg voice "${images[credit-support-agent]}" \
  --arg generator "${images[data-generator]}" \
  --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg cloud_sql_backup_id "${cloud_sql_backup_id}" \
  '{schema_version:1,status:(if $mode=="promote" then "promoted" else "qualified" end),mode:$mode,commit:$commit,environment:$environment,alembic_revision:$alembic,images:{"banking-service":$banking,"credit-support-agent":$voice,"data-generator":$generator},cutover:{final_cloud_sql_backup_id:(if $cloud_sql_backup_id=="" then null else $cloud_sql_backup_id end)},validation:{terraform:true,bootstrap:true,migration:true,reconciliation:true,reset_seed:true,datastream:true,federation:true,service_health:true},completed_at:$timestamp}' \
  > "${manifest_path}"
destination="gs://${PROJECT_ID}-fsi-release-manifests/alloydb/${RELEASE_COMMIT}/${RELEASE_MODE}.json"
gsutil cp "${manifest_path}" "${destination}"
echo "Release manifest: ${destination}"
