#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
ROOT_DIR=$(dirname "$(dirname "$SCRIPT_DIR")")

export VIEW_ROOT="${VIEW_ROOT:-${ROOT_DIR}/deployment/bigquery/${CURATED_DATASET:-analytics_curated}}"

echo "bootstrap_curated_views.sh is retained for compatibility."
echo "Delegating to idempotent lakehouse view reconciliation."

python3 "${SCRIPT_DIR}/reconcile_lakehouse_views.py"
