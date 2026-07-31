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
