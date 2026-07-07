#!/usr/bin/env bash
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

# Derive project root directory (parent of the scripts directory where this script resides)
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
ROOT_DIR=$(dirname "$(dirname "$SCRIPT_DIR")")

# ==========================================
# CONFIGURATION
# ==========================================
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
INSTANCE_NAME="${INSTANCE_NAME:-banking-data}"
BASTION_VM_NAME="${BASTION_VM_NAME:-fsi-gecx-vpc-jump-instance}"
BASTION_ZONE="${BASTION_ZONE:-us-central1-a}" 
LOCAL_PORT="${LOCAL_PORT:-5432}"
SOCKS_PORT="${SOCKS_PORT:-1080}"

INSTANCE_CONNECTION_NAME="$PROJECT_ID:$REGION:$INSTANCE_NAME"

# Check if project ID is available
if [ -z "$PROJECT_ID" ]; then
    echo "Error: Project ID is not configured. Please set PROJECT_ID environment variable or run 'gcloud config set project'." >&2
    exit 1
fi

echo "============================================================"
# 1. Stop CDC Streams
echo "[1/6] Stopping Datastream CDC stream..."
gcloud datastream streams update banking-cdc-stream \
    --location="${REGION}" \
    --state=PAUSED \
    --update-mask=state \
    --project="${PROJECT_ID}"

# ==========================================
# PROXY TUNNEL SETUP & CLEANUP
# ==========================================
SSH_TUNNEL_PID=""
PROXY_PID=""

cleanup() {
  echo ""
  echo "------------------------------------------------------------"
  echo "Executing cleanup..."
  if [ -n "$PROXY_PID" ]; then
    echo "Stopping Cloud SQL Auth Proxy (PID: $PROXY_PID)..."
    kill "$PROXY_PID" 2>/dev/null || true
  fi
  if [ -n "$SSH_TUNNEL_PID" ]; then
    echo "Stopping SOCKS5 SSH Tunnel (PID: $SSH_TUNNEL_PID)..."
    kill "$SSH_TUNNEL_PID" 2>/dev/null || true
  fi
  echo "Cleanup completed."
  echo "============================================================"
}

trap cleanup EXIT

# 2. Verify / Download Cloud SQL Auth Proxy
PROXY_BIN="$ROOT_DIR/scripts/ssh-tunnel/cloud-sql-proxy"
if [ ! -f "$PROXY_BIN" ]; then
    echo "[2/6] Cloud SQL Auth Proxy not found in scripts/ssh-tunnel/, downloading to /tmp/cloud-sql-proxy..."
    PROXY_BIN="/tmp/cloud-sql-proxy"
    if [ ! -f "$PROXY_BIN" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            ARCH="amd64"
            if [[ "$(uname -m)" == "arm64" ]]; then
                ARCH="arm64"
            fi
            curl -s -o "$PROXY_BIN" "https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.0/cloud-sql-proxy.darwin.${ARCH}"
        else
            curl -s -o "$PROXY_BIN" https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.11.0/cloud-sql-proxy.linux.amd64
        fi
        chmod +x "$PROXY_BIN"
    fi
else
    echo "[2/6] Using existing Cloud SQL Auth Proxy binary from scripts/ssh-tunnel/"
fi

# 3. Start SSH and DB Proxy
echo "[3/6] Starting SOCKS5 SSH Tunnel and Cloud SQL Auth Proxy..."
gcloud compute ssh "$BASTION_VM_NAME" \
    --zone="$BASTION_ZONE" \
    --project="${PROJECT_ID}" \
    --tunnel-through-iap \
    -- -N -D "$SOCKS_PORT" &
SSH_TUNNEL_PID=$!

sleep 2

ALL_PROXY="socks5://127.0.0.1:$SOCKS_PORT" "$PROXY_BIN" \
    --auto-iam-authn \
    --private-ip \
    --port="$LOCAL_PORT" \
    "$INSTANCE_CONNECTION_NAME" &
PROXY_PID=$!

echo "Waiting for proxies to initialize..."
sleep 5

# 4. Drop Schemas
echo "[4/6] Connecting to local DB proxy and dropping custom schemas..."
echo "Retrieving database owner password from Secret Manager..."
DB_PASSWORD=$(gcloud secrets versions access latest --secret="postgres_banking_root_password" --project="${PROJECT_ID}")
DB_PASSWORD="${DB_PASSWORD}" "$ROOT_DIR/banking-service/.venv/bin/python3" "$SCRIPT_DIR/drop_schemas.py"

# 5. Stop Proxies (Triggers cleanup hook early)
cleanup
trap - EXIT

# 6. Execute DB Migration Job
echo "[5/6] Invoking Cloud Run database migration job..."
gcloud run jobs execute banking-db-migrate \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --wait

# 7. Re-enable CDC Streams
echo "[6/6] Re-enabling Datastream CDC stream..."
gcloud datastream streams update banking-cdc-stream \
    --location="${REGION}" \
    --state=RUNNING \
    --update-mask=state \
    --project="${PROJECT_ID}"

echo "Database reset and migration completed successfully!"
echo "============================================================"
