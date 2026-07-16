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

existing_users="$(
  gcloud alloydb users list \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --cluster "${CLUSTER_ID}" \
    --format=json
)"

for group in "${iam_groups[@]}"; do
  if jq -e --arg group "${group}" \
    '[.. | strings | select(. == $group or endswith("/users/" + $group))] | length > 0' \
    <<<"${existing_users}" >/dev/null; then
    continue
  fi

  gcloud alloydb users create "${group}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --cluster "${CLUSTER_ID}" \
    --type IAM_GROUP \
    --db-roles alloydbiamuser \
    --quiet
done
