#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

# ==========================================
# CONFIGURATION
# ==========================================
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
INSTANCE_NAME="${INSTANCE_NAME:-banking-data}"
BASTION_VM_NAME="${BASTION_VM_NAME:-fsi-gecx-vpc-jump-instance}"
BASTION_ZONE="${BASTION_ZONE:-us-central1-a}" 
LOCAL_PORT="${LOCAL_PORT:-5432}"

INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:$INSTANCE_NAME"

echo "------------------------------------------------"
echo " Starting Connection Setup to: $INSTANCE_NAME "
echo "------------------------------------------------"

# 1. Ensure logged into Google Cloud
echo "[1/4] Checking gcloud authentication..."
if ! gcloud auth application-default print-access-token &>/dev/null; then
    echo "No valid Application Default Credentials found. Logging in..."
    gcloud auth application-default login --no-launch-browser
else
    echo "Application Default Credentials are valid."
fi

# 2. Download the Cloud SQL Auth Proxy locally if it doesn't exist
if [ ! -f ./cloud-sql-proxy ]; then
    echo "[2/4] Downloading Cloud SQL Auth Proxy..."
    # Auto-detects OS (macOS/Linux) and downloads v2
    if [[ "$OSTYPE" == "darwin"* ]]; then
        ARCH="amd64"
        if [[ "$(uname -m)" == "arm64" ]]; then
            ARCH="arm64"
        fi
        curl -o cloud-sql-proxy "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.0/cloud-sql-proxy.darwin.${ARCH}"
    else
        curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.0/cloud-sql-proxy.linux.amd64
    fi
    chmod +x cloud-sql-proxy
else
    echo "[2/4] Cloud SQL Auth Proxy already downloaded."
fi

# 3. Start SOCKS5 proxy via SSH tunnel to the bastion VM
SOCKS_PORT="1080"
echo "[3/4] Establishing SOCKS5 proxy tunnel to bastion VM $BASTION_VM_NAME on port $SOCKS_PORT..."
gcloud compute ssh "$BASTION_VM_NAME" \
    --zone="$BASTION_ZONE" \
    --tunnel-through-iap \
    -- -N -D "$SOCKS_PORT" &
SSH_TUNNEL_PID=$!

# Ensure the SSH tunnel process is killed when the script exits
trap 'kill $SSH_TUNNEL_PID' EXIT

# Give the tunnel a moment to establish
sleep 2

# 4. Start the Cloud SQL Proxy utilizing IAM Auth through SOCKS5 proxy
echo "[4/4] Starting Cloud SQL Auth Proxy on local port $LOCAL_PORT..."
echo "--> You can now connect your SQL client to localhost:$LOCAL_PORT"
echo "--> Use your IAM Email as the username, and leave the password BLANK."
echo "------------------------------------------------"

# Run the proxy using SOCKS5 proxy environment variable
ALL_PROXY="socks5://127.0.0.1:$SOCKS_PORT" ./cloud-sql-proxy \
    --auto-iam-authn \
    --private-ip \
    --port="$LOCAL_PORT" \
    "$INSTANCE_CONNECTION_NAME"
