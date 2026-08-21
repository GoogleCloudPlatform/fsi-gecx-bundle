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

network_attachment="${DATASTREAM_PSC_NETWORK_ATTACHMENT:-datastream-psc-attachment}"
discovery_id="${DATASTREAM_PSC_DISCOVERY_ID:-datastream-psc-discovery}"
attachment_uri="projects/${PROJECT_ID}/regions/${REGION}/networkAttachments/${network_attachment}"

command -v gcloud >/dev/null || {
  echo "gcloud is required." >&2
  exit 1
}
command -v jq >/dev/null || {
  echo "jq is required." >&2
  exit 1
}

gcloud compute network-attachments describe "${network_attachment}" \
  --project="${PROJECT_ID}" --region="${REGION}" >/dev/null

result="$(gcloud datastream private-connections create "${discovery_id}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --display-name="Datastream PSC producer discovery" \
  --network-attachment="${attachment_uri}" \
  --validate-only \
  --format=json)"

tenant_project="$(jq -er '
  [
    .metadata.validationResult.validations[]?.message[]?.metadata.tenant_project_id
    | select(type == "string" and length > 0)
  ]
  | unique
  | if length == 1 then .[0] else error("expected exactly one tenant project") end
' <<<"${result}")" || {
  echo "Datastream did not return exactly one tenant project:" >&2
  jq '.metadata.validationResult // .' <<<"${result}" >&2
  exit 1
}

printf '%s\n' "${tenant_project}"
printf '%s\n' \
  "Record this value in datastream_psc_producer_accept_lists for ${PROJECT_ID}, then apply Terraform." >&2
