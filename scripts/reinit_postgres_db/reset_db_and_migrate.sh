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
: "${PROJECT_ID:?Set PROJECT_ID or configure the active gcloud project.}"

root="$(git rev-parse --show-toplevel)"
PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
  "${root}/deployment/scripts/reconcile_datastream_after_reset.sh" pause

for job in banking-db-bootstrap banking-db-migrate banking-db-reconcile banking-db-reset; do
  gcloud run jobs execute "${job}" --project "${PROJECT_ID}" --region "${REGION}" --wait
done

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
  "${root}/deployment/scripts/reconcile_alloydb_federation.sh"

PROJECT_ID="${PROJECT_ID}" REGION="${REGION}" \
  "${root}/deployment/scripts/reconcile_datastream_after_reset.sh" rebuild

gcloud run jobs execute lakehouse-view-reconcile \
  --project "${PROJECT_ID}" --region "${REGION}" --wait

echo "AlloyDB lifecycle, reset/seed, federation, CDC backfill, and curated views completed."
