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

set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPONENT="${1:-all}"

run_banking_contract() {
  cd "${REPOSITORY_ROOT}/banking-service"
  uv run --frozen pytest -q \
    tests/test_action_proposals.py \
    tests/test_action_proposal_context.py \
    tests/test_mcp_tool_surface.py \
    tests/test_fraud_triage_workflow.py \
    tests/test_ces_session_capability.py \
    tests/test_ces_session_bootstrap.py \
    tests/test_ces_callback_bundle.py \
    tests/test_voice_bidi.py \
    tests/test_voice_deployment_contract.py \
    tests/test_database_schema_contract.py
}

run_adk_contract() {
  cd "${REPOSITORY_ROOT}/adk-agent/credit-support-agent"
  GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-action-proposal-contract-test}" \
    uv run --frozen pytest -q \
      tests/test_action_proposal_adapter.py \
      tests/test_workflow_authorization.py \
      tests/test_workflow_plugin.py \
      tests/test_live_authorization_reconciliation.py \
      tests/test_closeout.py \
      tests/test_no_semantic_gating.py \
      tests/test_trajectory_eval.py \
      tests/test_ces_trajectory.py \
      tests/test_ces_voice_qualification.py
}

case "${COMPONENT}" in
  banking)
    run_banking_contract
    ;;
  adk)
    run_adk_contract
    ;;
  all)
    run_banking_contract
    run_adk_contract
    ;;
  *)
    echo "Usage: $0 [banking|adk|all]" >&2
    exit 2
    ;;
esac
