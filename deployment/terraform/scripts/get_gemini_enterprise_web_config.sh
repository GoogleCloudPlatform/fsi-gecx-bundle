#!/bin/bash
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

PROJECT_ID=$1
LOCATION=$2
ENGINE_ID=$3

if [[ "$LOCATION" == "global" ]]; then
  API_HOST="discoveryengine.googleapis.com"
else
  API_HOST="${LOCATION}-discoveryengine.googleapis.com"
fi

ACCESS_TOKEN=$(gcloud auth print-access-token)
RESPONSE_FILE=$(mktemp)
trap 'rm -f "$RESPONSE_FILE"' EXIT

RESOURCE="projects/${PROJECT_ID}/locations/${LOCATION}/collections/default_collection/engines/${ENGINE_ID}/widgetConfigs/default_search_widget_config"
HTTP_STATUS=$(curl --silent --show-error \
  --output "$RESPONSE_FILE" \
  --write-out '%{http_code}' \
  --header "Authorization: Bearer ${ACCESS_TOKEN}" \
  --header "x-goog-user-project: ${PROJECT_ID}" \
  "https://${API_HOST}/v1alpha/${RESOURCE}")

if [[ "$HTTP_STATUS" != "200" ]]; then
  echo "Unable to resolve the Gemini Enterprise web configuration for ${ENGINE_ID} (HTTP ${HTTP_STATUS})." >&2
  cat "$RESPONSE_FILE" >&2
  exit 1
fi

CONFIG_ID=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("configId", ""))' "$RESPONSE_FILE")

if [[ -z "$CONFIG_ID" ]]; then
  echo "Gemini Enterprise widget configuration for ${ENGINE_ID} did not return configId." >&2
  exit 1
fi

printf '{"config_id":"%s"}\n' "$CONFIG_ID"
