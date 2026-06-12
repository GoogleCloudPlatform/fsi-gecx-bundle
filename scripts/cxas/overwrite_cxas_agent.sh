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

# Configuration
BASE_URL="https://ces.clients6.google.com/v1beta"
PROJECT_ID="${PROJECT_ID}"
APP_ID="${APP_ID}"
LOCATION="us"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="${SCRIPT_DIR}/../../gecx" # Directory containing your agent configs
AGENT_FOLDER="${AGENT_FOLDER:-Nova_Horizon_Bot_v2}"
ZIP_OUT="/tmp/agent_export.zip"

# Check required parameters
if [ -z "$PROJECT_ID" ]; then
  echo "Error: PROJECT_ID environment variable is required."
  exit 1
fi

if [ -z "$APP_ID" ]; then
  echo "Error: APP_ID environment variable is required."
  exit 1
fi

# Clean up the temporary zip file on exit
trap 'rm -f "$ZIP_OUT"' EXIT

# 1. Compress the directory structure
# We change directory (cd) first so that the root of the ZIP is the actual agent files, not the parent folder.
(cd "$AGENT_DIR" && zip -rq "$ZIP_OUT" "$AGENT_FOLDER" -x "*.DS_Store" "*.tftpl" ".gitignore")

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
  "${BASE_URL}/projects/${PROJECT_ID}/locations/us/apps:importApp")

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

# 7. Get the list of existing deployments
echo "Retrieving existing deployments..."
DEPLOYMENTS_RESPONSE=$(curl -s \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "x-goog-user-project: $PROJECT_ID" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}/deployments")

# Extract deployment names
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

if [ -z "$DEPLOYMENT_NAMES" ]; then
  echo "No existing deployments found for App ID $APP_ID."
else
  echo "Found existing deployments:"
  echo "$DEPLOYMENT_NAMES"
fi

# 8. Create a new agent version
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

# 9. Update the existing deployments to use the new version
if [ -n "$DEPLOYMENT_NAMES" ]; then
  echo "$DEPLOYMENT_NAMES" | while read -r DEPLOYMENT_NAME; do
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
      else
        echo "Error: Failed to update deployment $(basename "$DEPLOYMENT_NAME")."
        echo "Response: $PATCH_RESPONSE"
      fi
    fi
  done
else
  echo "Warning: No existing deployments were updated because none were found."
fi

