#!/usr/bin/env bash
set -euo pipefail

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

# Configuration
BASE_URL="${BASE_URL:-https://ces.clients6.google.com/v1beta}"
PROJECT_ID="${PROJECT_ID:-}"
APP_ID="${APP_ID:-}"
LOCATION="${LOCATION:-us}"
BANKING_SERVICE_REGION="${BANKING_SERVICE_REGION:-us-central1}"
BANKING_SERVICE_URL="${BANKING_SERVICE_URL:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="${SCRIPT_DIR}/../../gecx" # Directory containing your agent configs
AGENT_FOLDER="${AGENT_FOLDER:-Nova_Horizon_Bot_v2}"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cxas-agent-overwrite.XXXXXX")"
ZIP_OUT="${TEMP_DIR}/agent_export.zip"
UPDATED_DEPLOYMENTS_FILE="${TEMP_DIR}/updated_deployments.txt"
EXPECTED_MODEL="${EXPECTED_MODEL:-}"
TARGET_DEPLOYMENT_NAME="${TARGET_DEPLOYMENT_NAME:-}"
RESULT_FILE="${RESULT_FILE:-}"

cleanup() {
  rm -rf -- "$TEMP_DIR"
}
trap cleanup EXIT

if [ -z "$EXPECTED_MODEL" ]; then
  EXPECTED_MODEL=$(awk '
    /^modelSettings:/ { in_model_settings = 1; next }
    in_model_settings && /^  model:/ { print $2; exit }
    in_model_settings && /^[^ ]/ { exit }
  ' "$AGENT_DIR/$AGENT_FOLDER/app.yaml")
fi

# Check required parameters
if [ -z "$PROJECT_ID" ]; then
  echo "Error: PROJECT_ID environment variable is required."
  exit 1
fi

if [ -z "$APP_ID" ]; then
  echo "Error: APP_ID environment variable is required."
  exit 1
fi

# CES imports consume rendered YAML, while environment-specific generated files
# remain intentionally ignored by Git. Materialize the MCP toolset immediately
# before packaging so a clean checkout is independently deployable.
TOOLSET_TEMPLATE="$AGENT_DIR/$AGENT_FOLDER/toolsets/banking_service_mcp_toolset/banking_service_mcp_toolset.yaml.tftpl"
if [ -f "$TOOLSET_TEMPLATE" ]; then
  if [ -z "$BANKING_SERVICE_URL" ]; then
    BANKING_SERVICE_URL=$(gcloud run services describe banking-service \
      --project "$PROJECT_ID" \
      --region "$BANKING_SERVICE_REGION" \
      --format='value(status.url)')
  fi
  if [ -z "$BANKING_SERVICE_URL" ]; then
    echo "Error: Could not resolve the banking-service URL for the CES toolset." >&2
    exit 1
  fi
  python3 "$SCRIPT_DIR/materialize_agent_bundle.py" \
    --agent-folder "$AGENT_DIR/$AGENT_FOLDER" \
    --banking-service-url "$BANKING_SERVICE_URL"
fi

# 1. Compress the directory structure
# We change directory (cd) first so that the root of the ZIP is the actual agent files, not the parent folder.
(cd "$AGENT_DIR" && zip -rq "$ZIP_OUT" "$AGENT_FOLDER" \
  -x "*.DS_Store" "*.tftpl" ".gitignore" "*/__pycache__/*" "*.pyc" "*.pyo")

# 2. Convert the ZIP file to a Base64-encoded string
BASE64_CONTENT=$(cat "$ZIP_OUT" | base64 | tr -d '\n')

# 3. Get your active GCP authentication token
ACCESS_TOKEN=$(gcloud auth print-access-token)

# 4. Construct the JSON payload with overwrite strategy
PAYLOAD=$(cat <<EOF
{
  "appContent": "$BASE64_CONTENT",
  "appId": "$APP_ID",
  "importOptions": {
    "conflictResolutionStrategy": "OVERWRITE"
  }
}
EOF
)

# 5. Call the Google CES importApp REST API
echo "Uploading and overwriting agent in Google Cloud..."
RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-goog-user-project: $PROJECT_ID" \
  -d "$PAYLOAD" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps:importApp")

# Extract operation name
OPERATION_NAME=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('name', ''))")

if [ -z "$OPERATION_NAME" ]; then
  echo "Error: Failed to get operation name from response."
  echo "Response: $RESPONSE"
  exit 1
fi

echo "Operation Name: $OPERATION_NAME"

# Polling loop
echo "Waiting for operation to complete..."
while true; do
  STATUS_RESPONSE=$(curl -s \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "x-goog-user-project: $PROJECT_ID" \
    "${BASE_URL}/${OPERATION_NAME}")

  DONE=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('done', False))")
  
  if [ "$DONE" = "True" ]; then
    echo "Operation complete!"
    # Check for errors
    ERROR=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', ''))")
    if [ -n "$ERROR" ]; then
      echo "Operation failed with error: $ERROR"
      exit 1
    fi
    break
  fi

  echo "Still working... sleeping for 5 seconds"
  sleep 5
done

# 6. Verify/extract App ID from status response
APP_ID_FROM_RESPONSE=$(echo "$STATUS_RESPONSE" | python3 -c "
import sys, json
try:
    status_data = json.load(sys.stdin)
    response_data = status_data.get('response', {})
    app = response_data.get('name')
    if app:
        print(app.split('/')[-1])
        sys.exit(0)
except Exception:
    pass
")

if [ -n "$APP_ID_FROM_RESPONSE" ] && [ "$APP_ID_FROM_RESPONSE" != "$APP_ID" ]; then
  echo "Warning: Extracted App ID ($APP_ID_FROM_RESPONSE) does not match expected App ID ($APP_ID)."
  APP_ID="$APP_ID_FROM_RESPONSE"
fi

echo "App ID: $APP_ID"

# 7. Verify the imported root-agent model before creating or moving a deployment.
if [ -n "$EXPECTED_MODEL" ]; then
  echo "Verifying imported root-agent model is $EXPECTED_MODEL..."
  APP_RESPONSE=$(curl -s \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "x-goog-user-project: $PROJECT_ID" \
    "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}")

  ACTUAL_APP_MODEL=$(echo "$APP_RESPONSE" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('modelSettings', {}).get('model', ''))
except Exception:
    pass
")

  if [ "$ACTUAL_APP_MODEL" != "$EXPECTED_MODEL" ]; then
    echo "Error: Imported app model is '$ACTUAL_APP_MODEL'; expected '$EXPECTED_MODEL'."
    echo "App response: $APP_RESPONSE"
    exit 1
  fi

  ROOT_AGENT_NAME=$(echo "$APP_RESPONSE" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('rootAgent', ''))
except Exception:
    pass
")

  if [ -z "$ROOT_AGENT_NAME" ]; then
    echo "Error: Imported app did not report a root agent."
    echo "Response: $APP_RESPONSE"
    exit 1
  fi

  AGENT_RESPONSE=$(curl -s \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "x-goog-user-project: $PROJECT_ID" \
    "${BASE_URL}/${ROOT_AGENT_NAME}")

  ACTUAL_MODEL=$(echo "$AGENT_RESPONSE" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('modelSettings', {}).get('model', ''))
except Exception:
    pass
")

  if [ "$ACTUAL_MODEL" != "$EXPECTED_MODEL" ]; then
    echo "Error: Imported root-agent model is '$ACTUAL_MODEL'; expected '$EXPECTED_MODEL'."
    echo "Agent response: $AGENT_RESPONSE"
    exit 1
  fi

  echo "Verified imported app and root-agent model: $ACTUAL_MODEL"
fi

# 8. Resolve the deployment that this release is allowed to move.
if [ -n "$TARGET_DEPLOYMENT_NAME" ]; then
  EXPECTED_DEPLOYMENT_PREFIX="projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}/deployments/"
  case "$TARGET_DEPLOYMENT_NAME" in
    "$EXPECTED_DEPLOYMENT_PREFIX"*) ;;
    *)
      echo "Error: TARGET_DEPLOYMENT_NAME is outside app $APP_ID: $TARGET_DEPLOYMENT_NAME"
      exit 1
      ;;
  esac
  DEPLOYMENTS_RESPONSE=$(curl -s \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "x-goog-user-project: $PROJECT_ID" \
    "${BASE_URL}/${TARGET_DEPLOYMENT_NAME}")
  DEPLOYMENT_NAMES=$(echo "$DEPLOYMENTS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('name', ''))
except Exception as e:
    sys.stderr.write(f'Error parsing deployment: {e}\n')
")
  if [ "$DEPLOYMENT_NAMES" != "$TARGET_DEPLOYMENT_NAME" ]; then
    echo "Error: Target CES deployment does not exist: $TARGET_DEPLOYMENT_NAME"
    echo "Response: $DEPLOYMENTS_RESPONSE"
    exit 1
  fi
else
  echo "Retrieving existing deployments..."
  DEPLOYMENTS_RESPONSE=$(curl -s \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "x-goog-user-project: $PROJECT_ID" \
    "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}/deployments")
  DEPLOYMENT_NAMES=$(echo "$DEPLOYMENTS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    deployments = data.get('deployments', [])
    for dep in deployments:
        name = dep.get('name')
        if name:
            print(name)
except Exception as e:
    sys.stderr.write(f'Error parsing deployments: {e}\n')
")
fi

if [ -z "$DEPLOYMENT_NAMES" ]; then
  echo "No existing deployments found for App ID $APP_ID."
else
  echo "Found existing deployments:"
  echo "$DEPLOYMENT_NAMES"
fi

# 9. Create a new agent version
echo "Creating a new agent version..."
VERSION_TIMESTAMP=$(date +"%-m/%-d/%Y, %-I:%M:%S %p")
CREATE_VERSION_RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-goog-user-project: $PROJECT_ID" \
  -d "{\"description\":\"Automatically created from deploying to platform via overwrite\",\"displayName\":\"deployment-version-$VERSION_TIMESTAMP\"}" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}/versions")

# Extract the version name (resource path)
VERSION_RESOURCE_NAME=$(echo "$CREATE_VERSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('name', ''))")

if [ -z "$VERSION_RESOURCE_NAME" ]; then
  echo "Error: Failed to extract version resource name from response."
  echo "Response: $CREATE_VERSION_RESPONSE"
  exit 1
fi
echo "New Version Resource Name: $VERSION_RESOURCE_NAME"

# 10. Update the existing deployments to use the new version
: > "$UPDATED_DEPLOYMENTS_FILE"
if [ -n "$DEPLOYMENT_NAMES" ]; then
  while read -r DEPLOYMENT_NAME; do
    if [ -n "$DEPLOYMENT_NAME" ]; then
      echo "Updating deployment $DEPLOYMENT_NAME to use version $VERSION_RESOURCE_NAME..."
      PATCH_RESPONSE=$(curl -s -X PATCH \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json; charset=utf-8" \
        -H "x-goog-user-project: $PROJECT_ID" \
        -d "{\"appVersion\":\"$VERSION_RESOURCE_NAME\"}" \
        "${BASE_URL}/${DEPLOYMENT_NAME}?updateMask=appVersion")
      
      UPDATED_VERSION=$(echo "$PATCH_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('appVersion', ''))
except Exception:
    pass
")
      if [ "$UPDATED_VERSION" = "$VERSION_RESOURCE_NAME" ]; then
        echo "Successfully updated deployment $(basename "$DEPLOYMENT_NAME")."
        echo "$DEPLOYMENT_NAME" >> "$UPDATED_DEPLOYMENTS_FILE"
      else
        echo "Error: Failed to update deployment $(basename "$DEPLOYMENT_NAME")."
        echo "Response: $PATCH_RESPONSE"
        exit 1
      fi
    fi
  done <<< "$DEPLOYMENT_NAMES"
else
  echo "Error: No existing deployments were found; the new CES version was not released."
  exit 1
fi

if [ -n "$RESULT_FILE" ]; then
  python3 - "$RESULT_FILE" "$PROJECT_ID" "$LOCATION" "$APP_ID" \
    "$VERSION_RESOURCE_NAME" "$EXPECTED_MODEL" "$UPDATED_DEPLOYMENTS_FILE" <<'PY'
import json
from pathlib import Path
import sys

result_file, project, location, app_id, version, model, deployments_file = sys.argv[1:]
deployments = [
    line for line in Path(deployments_file).read_text().splitlines() if line
]
payload = {
    "app": f"projects/{project}/locations/{location}/apps/{app_id}",
    "version": version,
    "deployments": deployments,
    "model": model,
}
Path(result_file).write_text(json.dumps(payload, sort_keys=True) + "\n")
PY
  echo "CES release result: $RESULT_FILE"
fi
