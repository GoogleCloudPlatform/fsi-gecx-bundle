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
LOCATION="us"
AGENT_DIR="../../gecx" # Directory containing your agent configs
AGENT_FOLDER="${AGENT_FOLDER:-Credit_Support_Voice_Agent}"
ZIP_OUT="/tmp/voice_agent_export.zip"

# Clean up the temporary zip file on exit
trap 'rm -f "$ZIP_OUT"' EXIT

if [ -z "$PROJECT_ID" ]; then
  echo "Error: PROJECT_ID environment variable is not set."
  echo "Usage: PROJECT_ID=my-project-id ./deploy_voice_agent.sh"
  exit 1
fi

# 1. Compress the directory structure
# We change directory (cd) first so that the root of the ZIP is the actual agent files, not the parent folder.
echo "Compressing agent configuration from $AGENT_DIR/$AGENT_FOLDER..."
(cd "$AGENT_DIR" && zip -rq "$ZIP_OUT" "$AGENT_FOLDER" -x "*.DS_Store" "*.tftpl" ".gitignore")

# 2. Convert the ZIP file to a Base64-encoded string
BASE64_CONTENT=$(cat "$ZIP_OUT" | base64 | tr -d '\n')

# 3. Get your active GCP authentication token
ACCESS_TOKEN=$(gcloud auth print-access-token)

# 4. Construct the JSON payload
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
PAYLOAD=$(cat <<EOF
{
  "displayName": "${AGENT_FOLDER}_$TIMESTAMP",
  "appContent": "$BASE64_CONTENT"
}
EOF
)

# 5. Call the Google CES importApp REST API
echo "Uploading and importing agent to Google Cloud..."
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

# 6. Extract the App ID
APP_ID=$(echo "$STATUS_RESPONSE" | python3 -c "
import sys, json
try:
    status_data = json.load(sys.stdin)
    response_data = status_data.get('response')
    app = response_data.get('name')
    if app:
        print(app.split('/')[-1])
        sys.exit(0)
except Exception:
    pass
")

if [ -z "$APP_ID" ]; then
  echo "Error: Failed to extract app ID from operation response."
  exit 1
fi
echo "App ID: $APP_ID"

# 7. Create a new agent version
echo "Creating a new agent version..."
VERSION_TIMESTAMP=$(date +"%-m/%-d/%Y, %-I:%M:%S %p")
CREATE_VERSION_RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-goog-user-project: $PROJECT_ID" \
  -d "{\"description\":\"Automatically created from voice agent deploy script\",\"displayName\":\"voice-agent-version-$VERSION_TIMESTAMP\"}" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}/versions")

# Extract the version name (resource path)
VERSION_RESOURCE_NAME=$(echo "$CREATE_VERSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('name', ''))")

if [ -z "$VERSION_RESOURCE_NAME" ]; then
  echo "Error: Failed to extract version resource name from response."
  echo "Response: $CREATE_VERSION_RESPONSE"
  exit 1
fi
echo "Version Resource Name: $VERSION_RESOURCE_NAME"

# 8. Create an API deployment
echo "Creating API deployment..."
DEPLOYMENT_PAYLOAD=$(cat <<EOF
{
  "appVersion": "$VERSION_RESOURCE_NAME",
  "channelProfile": {
    "channelType": "API",
    "disableBargeInControl": false,
    "disableDtmf": false
  },
  "displayName": "Voice API Channel"
}
EOF
)

CREATE_DEPLOYMENT_RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-goog-user-project: $PROJECT_ID" \
  -d "$DEPLOYMENT_PAYLOAD" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}/deployments")

# Extract the deployment name (resource path)
DEPLOYMENT_NAME=$(echo "$CREATE_DEPLOYMENT_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    name = data.get('name')
    if name:
        print(name)
except Exception:
    pass
")

if [ -z "$DEPLOYMENT_NAME" ]; then
  echo "Error: Failed to extract deployment ID from response."
  echo "Response: $CREATE_DEPLOYMENT_RESPONSE"
  exit 1
fi
echo "Deployment Name: $DEPLOYMENT_NAME"

# 9. Output in the requested format
cat << EOF

Copy into terraform.tfvars file:

gecx_voice_agent_id = "${DEPLOYMENT_NAME}"
EOF
