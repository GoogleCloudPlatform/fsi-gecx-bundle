#!/usr/bin/env bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?PROJECT_ID is required}"
REGION="${REGION:-us-central1}"
CLUSTER_ID="${ALLOYDB_CLUSTER_ID:-banking-data}"

mapfile -t iam_groups < <(
  terraform -chdir=deployment/terraform output -json alloydb_iam_group_users |
    jq -r '.[]'
)

if [[ "${#iam_groups[@]}" -eq 0 ]]; then
  exit 0
fi

parent="projects/${PROJECT_ID}/locations/${REGION}/clusters/${CLUSTER_ID}"
api_root="https://alloydb.googleapis.com/v1beta/${parent}/users"
access_token="$(gcloud auth print-access-token)"
existing_users="$(
  curl --fail --silent --show-error \
    -H "Authorization: Bearer ${access_token}" \
    "${api_root}"
)"

for group in "${iam_groups[@]}"; do
  if jq -e --arg group "${group}" \
    '[.. | strings | select(. == $group or endswith("/users/" + $group))] | length > 0' \
    <<<"${existing_users}" >/dev/null; then
    continue
  fi

  encoded_group="$(jq -rn --arg value "${group}" '$value | @uri')"
  curl --fail --silent --show-error \
    -X POST \
    -H "Authorization: Bearer ${access_token}" \
    -H "Content-Type: application/json" \
    -d '{"userType":"ALLOYDB_IAM_GROUP"}' \
    "${api_root}?userId=${encoded_group}" >/dev/null
done
