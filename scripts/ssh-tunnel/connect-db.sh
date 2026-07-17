#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
CLUSTER_ID="${CLUSTER_ID:-banking-data}"
INSTANCE_ID="${INSTANCE_ID:-banking-primary}"
BASTION_VM_NAME="${BASTION_VM_NAME:-fsi-gecx-vpc-jump-instance}"
BASTION_ZONE="${BASTION_ZONE:-us-central1-a}"
LOCAL_PORT="${LOCAL_PORT:-5432}"

: "${PROJECT_ID:?Set PROJECT_ID or configure the active gcloud project.}"
alloydb_ip="$(gcloud alloydb instances describe "${INSTANCE_ID}" \
  --project "${PROJECT_ID}" --region "${REGION}" --cluster "${CLUSTER_ID}" \
  --format='value(ipAddress)')"

echo "Forwarding localhost:${LOCAL_PORT} to AlloyDB ${CLUSTER_ID}/${INSTANCE_ID} through ${BASTION_VM_NAME}."
echo "In another terminal, connect with:"
echo "  PGPASSWORD=\"\$(gcloud auth print-access-token)\" psql \"host=127.0.0.1 port=${LOCAL_PORT} dbname=banking user=\$(gcloud config get-value account) sslmode=require\""

exec gcloud compute ssh "${BASTION_VM_NAME}" \
  --project "${PROJECT_ID}" --zone "${BASTION_ZONE}" --tunnel-through-iap \
  -- -N -L "${LOCAL_PORT}:${alloydb_ip}:5432"
