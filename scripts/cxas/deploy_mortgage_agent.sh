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
AGENT_FOLDER="${AGENT_FOLDER:-Nova_Horizon_Bot_v2}"
ZIP_OUT="/tmp/agent_export.zip"

# Clean up the temporary zip file on exit
trap 'rm -f "$ZIP_OUT"' EXIT


# 1. Compress the directory structure
# We change directory (cd) first so that the root of the ZIP is the actual agent files, not the parent folder.
(cd "$AGENT_DIR" && zip -rq "$ZIP_OUT" "$AGENT_FOLDER" -x "*.DS_Store" "*.tftpl" ".gitignore")

# 2. Convert the ZIP file to a Base64-encoded string
BASE64_CONTENT=$(cat "$ZIP_OUT" | base64 | tr -d '\n')

# 3. Get your active GCP authentication token
ACCESS_TOKEN=$(gcloud auth print-access-token)

# 4. Construct the JSON payload
# Note: Adjust 'displayName' or remove it if you are updating an existing agent.
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
  "${BASE_URL}/projects/${PROJECT_ID}/locations/us/apps:importApp")

# echo "Response: $RESPONSE"

# Extract operation name
OPERATION_NAME=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('name', ''))")

if [ -z "$OPERATION_NAME" ]; then
  echo "Error: Failed to get operation name from response."
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
import sys, json, os
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
  echo "Error: Failed to extract app ID from operation response or local app.json."
  exit 1
fi
echo "App ID: $APP_ID"

# 7. Query tools for clientFunction.name = 'trigger_file_upload'
echo "Querying tools..."
TOOLS_RESPONSE=$(curl -s \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "x-goog-user-project: $PROJECT_ID" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}/tools?filter=include_system_tools=true")

TRIGGER_FILE_UPLOAD_TOOL_NAME=$(echo "$TOOLS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tools = data.get('tools', [])
    for tool in tools:
        if tool.get('clientFunction', {}).get('name') == 'trigger_file_upload':
            # print(json.dumps(tool, indent=2))
            print(tool.get('name'))
            sys.exit(0)
    print('Tool with clientFunction.name = \'trigger_file_upload\' not found.')
except Exception as e:
    print(f'Error parsing tools response: {e}')
")

echo "Trigger file upload tool name: $TRIGGER_FILE_UPLOAD_TOOL_NAME"

POPULATE_FORM_CONTENT_TOOL_NAME=$(echo "$TOOLS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tools = data.get('tools', [])
    for tool in tools:
        if tool.get('clientFunction', {}).get('name') == 'populate_form_content':
            # print(json.dumps(tool, indent=2))
            print(tool.get('name'))
            sys.exit(0)
    print('Tool with clientFunction.name = \'populate_form_content\' not found.')
except Exception as e:
    print(f'Error parsing tools response: {e}')
")

echo "Populate form content tool name: $POPULATE_FORM_CONTENT_TOOL_NAME"

GET_USER_LOCATION_TOOL_NAME=$(echo "$TOOLS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tools = data.get('tools', [])
    for tool in tools:
        if tool.get('clientFunction', {}).get('name') == 'get_user_location':
            # print(json.dumps(tool, indent=2))
            print(tool.get('name'))
            sys.exit(0)
    print('Tool with clientFunction.name = \'get_user_location\' not found.')
except Exception as e:
    print(f'Error parsing tools response: {e}')
")

echo "Get user location tool name: $GET_USER_LOCATION_TOOL_NAME"


# 8. Create a new agent version
echo "Creating a new agent version..."
VERSION_TIMESTAMP=$(date +"%-m/%-d/%Y, %-I:%M:%S %p")
CREATE_VERSION_RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-goog-user-project: $PROJECT_ID" \
  -d "{\"description\":\"Automatically created from deploying to platform\",\"displayName\":\"deployment-version-$VERSION_TIMESTAMP\"}" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}/versions")

# echo "Create Version Response: $CREATE_VERSION_RESPONSE"

# 9. Extract the version name (resource path)
VERSION_RESOURCE_NAME=$(echo "$CREATE_VERSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('name', ''))")

if [ -z "$VERSION_RESOURCE_NAME" ]; then
  echo "Error: Failed to extract version resource name from response."
  exit 1
fi
echo "Version Resource Name: $VERSION_RESOURCE_NAME"

# 10. Create a deployment
echo "Creating deployment..."
DEPLOYMENT_PAYLOAD=$(cat <<EOF
{
  "appVersion": "$VERSION_RESOURCE_NAME",
  "channelProfile": {
    "channelType": "CONTACT_CENTER_AS_A_SERVICE",
    "disableBargeInControl": false,
    "disableDtmf": false
  },
  "displayName": "CCaaS Channel"
}
EOF
)

CREATE_DEPLOYMENT_RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-goog-user-project: $PROJECT_ID" \
  -d "$DEPLOYMENT_PAYLOAD" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}/deployments")

# echo "Create Deployment Response: $CREATE_DEPLOYMENT_RESPONSE"

# 11. Extract the deployment ID
CCAAS_DEPLOYMENT_ID=$(echo "$CREATE_DEPLOYMENT_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    name = data.get('name')
    print(name)
except Exception:
    pass
")

if [ -z "$CCAAS_DEPLOYMENT_ID" ]; then
  echo "Error: Failed to extract deployment ID from response."
  exit 1
fi
echo "CCaaS Deployment Id: $CCAAS_DEPLOYMENT_ID"

# 12. Create a conversational profile
echo "Creating conversational profile..."
PROFILE_PAYLOAD=$(cat <<EOF
{
  "displayName": "mortgage_preapproval_bot_$TIMESTAMP",
  "languageCode": "en-US",
  "useBidiStreaming": true,
  "automatedAgentConfig": {
    "agent": "$CCAAS_DEPLOYMENT_ID"
  }
}
EOF
)

CREATE_PROFILE_RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-goog-user-project: $PROJECT_ID" \
  -d "$PROFILE_PAYLOAD" \
  "https://${LOCATION}-dialogflow.googleapis.com/v2beta1/projects/${PROJECT_ID}/locations/${LOCATION}/conversationProfiles")

# echo "Create Profile Response: $CREATE_PROFILE_RESPONSE"

# Extract conversational profile name (resource path)
CCAAS_CONVERSATIONAL_PROFILE_NAME=$(echo "$CREATE_PROFILE_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('name', ''))
except Exception:
    pass
")
echo "CCaaS Conversational Profile Name: $CCAAS_CONVERSATIONAL_PROFILE_NAME"

# 13. Create a Web widget deployment channel
echo "Creating Web widget deployment..."
WEB_WIDGET_PAYLOAD=$(cat <<EOF
{
  "appVersion": "$VERSION_RESOURCE_NAME",
  "channelProfile": {
    "channelType": "WEB_UI",
    "disableBargeInControl": false,
    "disableDtmf": false,
    "webWidgetConfig": {
      "modality": "CHAT_AND_VOICE",
      "securitySettings": {
        "allowedOrigins": [],
        "enableOriginCheck": false,
        "enablePublicAccess": true,
        "enableRecaptcha": false
      },
      "theme": "LIGHT",
      "webWidgetTitle": "Nova Horizon Assistant"
    }
  },
  "displayName": "Web widget Channel"
}
EOF
)

CREATE_WEB_WIDGET_RESPONSE=$(curl -s -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-goog-user-project: $PROJECT_ID" \
  -d "$WEB_WIDGET_PAYLOAD" \
  "${BASE_URL}/projects/${PROJECT_ID}/locations/${LOCATION}/apps/${APP_ID}/deployments")

WEB_WIDGET_DEPLOYMENT_ID=$(echo "$CREATE_WEB_WIDGET_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    name = data.get('name')
    if name:
        print(name)
except Exception:
    pass
")
echo "Web Widget Deployment ID: $WEB_WIDGET_DEPLOYMENT_ID"

cat << EOF

Copy into terraform.tfvars file:

cx_agent_studio_deployment_name  = "${WEB_WIDGET_DEPLOYMENT_ID}"
cx_agent_studio_upload_tool_name = "${TRIGGER_FILE_UPLOAD_TOOL_NAME}"
cx_agent_studio_populate_content_tool_name = "${POPULATE_FORM_CONTENT_TOOL_NAME}"
cx_agent_studio_get_user_location_tool_name = "${GET_USER_LOCATION_TOOL_NAME}"
EOF