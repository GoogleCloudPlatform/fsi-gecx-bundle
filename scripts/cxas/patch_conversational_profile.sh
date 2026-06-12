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

set -e

# Help message
usage() {
  echo "Usage: $0 -p PROJECT_ID -c CONVERSATIONAL_PROFILE_ID -d DEPLOYMENT_ID [-l LOCATION]"
  echo "  -p PROJECT_ID                  Google Cloud Project ID"
  echo "  -c CONVERSATIONAL_PROFILE_ID   The ID or full path of the Dialogflow Conversation Profile"
  echo "  -d DEPLOYMENT_ID               The new automated agent deployment ID or full path"
  echo "  -l LOCATION                    Dialogflow location/region (default: us)"
  exit 1
}

# Parse options
LOCATION="us"

while getopts "p:c:d:l:h" opt; do
  case ${opt} in
    p ) PROJECT_ID=$OPTARG ;;
    c ) CONVERSATIONAL_PROFILE_ID=$OPTARG ;;
    d ) DEPLOYMENT_ID=$OPTARG ;;
    l ) LOCATION=$OPTARG ;;
    h ) usage ;;
    \? ) usage ;;
  esac
done

# Check required parameters
if [ -z "$PROJECT_ID" ] || [ -z "$CONVERSATIONAL_PROFILE_ID" ] || [ -z "$DEPLOYMENT_ID" ]; then
  echo "Error: PROJECT_ID, CONVERSATIONAL_PROFILE_ID, and DEPLOYMENT_ID are required."
  usage
fi

# Normalize conversation profile path if only ID is provided
if [[ ! "$CONVERSATIONAL_PROFILE_ID" =~ ^projects/ ]]; then
  CONVERSATIONAL_PROFILE_PATH="projects/${PROJECT_ID}/locations/${LOCATION}/conversationProfiles/${CONVERSATIONAL_PROFILE_ID}"
else
  CONVERSATIONAL_PROFILE_PATH="$CONVERSATIONAL_PROFILE_ID"
fi

# Print out configuration
echo "Configuring conversation profile patch..."
echo "Project ID: $PROJECT_ID"
echo "Location: $LOCATION"
echo "Conversation Profile: $CONVERSATIONAL_PROFILE_PATH"
echo "New Deployment ID: $DEPLOYMENT_ID"

# Get GCP Auth Token
ACCESS_TOKEN=$(gcloud auth print-access-token)

# Construct JSON payload
PAYLOAD=$(cat <<EOF
{
  "automatedAgentConfig": {
    "agent": "$DEPLOYMENT_ID"
  }
}
EOF
)

# Call API to patch conversational profile
echo "Patching conversational profile..."
RESPONSE=$(curl -s -X PATCH \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -H "x-goog-user-project: $PROJECT_ID" \
  -d "$PAYLOAD" \
  "https://${LOCATION}-dialogflow.googleapis.com/v2beta1/${CONVERSATIONAL_PROFILE_PATH}?updateMask=automatedAgentConfig.agent")

echo "Response:"
if command -v python3 &>/dev/null; then
  echo "$RESPONSE" | python3 -m json.tool
else
  echo "$RESPONSE"
fi
