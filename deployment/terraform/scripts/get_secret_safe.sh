#!/bin/bash
SECRET_NAME=$1
PROJECT_ID=$2

# Attempt to access secret version payload
PAYLOAD=$(gcloud secrets versions access latest --secret="$SECRET_NAME" --project="$PROJECT_ID" 2>/dev/null)

if [ $? -eq 0 ]; then
  # Return JSON format to Terraform
  echo "{\"secret_data\": \"$PAYLOAD\"}"
else
  # Fallback value if secret doesn't exist or is empty
  echo "{\"secret_data\": \"\"}"
fi
