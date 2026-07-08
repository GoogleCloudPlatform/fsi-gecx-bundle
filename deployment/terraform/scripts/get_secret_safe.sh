#!/bin/bash
SECRET_NAME=$1
PROJECT_ID=$2

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
else
  # It is a real error (e.g. PERMISSION_DENIED, Network error, gcloud missing, etc.).
  # Print the error message to stderr so it shows up in Terraform's output, and exit with non-zero.
  echo "Error fetching secret $SECRET_NAME: $ERROR_MSG" >&2
  exit $EXIT_CODE
fi
