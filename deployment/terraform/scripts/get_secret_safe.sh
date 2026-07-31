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

SECRET_NAME=$1
PROJECT_ID=$2
IGNORE_DISABLED=$3

# Create a temporary file to capture stderr
STDERR_FILE=$(mktemp)
trap 'rm -f "$STDERR_FILE"' EXIT

# Attempt to access secret version payload
PAYLOAD=$(gcloud secrets versions access latest --secret="$SECRET_NAME" --project="$PROJECT_ID" 2>"$STDERR_FILE")
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
  # Return JSON format to Terraform
  echo "{\"secret_data\": \"$PAYLOAD\"}"
  exit 0
fi

# Read the error message
ERROR_MSG=$(cat "$STDERR_FILE")

# Check if the error is a 404 (NOT_FOUND)
if echo "$ERROR_MSG" | grep -q "NOT_FOUND"; then
  # Secret does not exist or has no versions. Return empty list fallback.
  echo "{\"secret_data\": \"\"}"
  exit 0
elif [ "$IGNORE_DISABLED" = "true" ] && echo "$ERROR_MSG" | grep -q "is in DISABLED state"; then
  # Secret version is disabled. Return empty list fallback.
  echo "{\"secret_data\": \"\"}"
  exit 0
else
  # It is a real error (e.g. PERMISSION_DENIED, Network error, gcloud missing, etc.).
  # Print the error message to stderr so it shows up in Terraform's output, and exit with non-zero.
  echo "Error fetching secret $SECRET_NAME: $ERROR_MSG" >&2
  exit $EXIT_CODE
fi
