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

from types import SimpleNamespace

import pytest

from agent import agent as agent_module
from agent.agent import (
    after_tool_callback,
    prepare_customer_reported_fraud_confirmation,
)
from agent.proposal_evidence import (
    COMMIT_IN_FLIGHT,
    create_pending_proposal,
)
from agent.workflow_authorization import (
    TRIAGE_CUSTOMER_REPORTED_FRAUD,
)


def test_prepare_customer_reported_fraud_binds_trusted_recent_selection() -> None:
    state = {
        "session_id": "voice-session-1",
        "fraud_playbook": {
            "entry_mode": "GENERAL_SUPPORT",
            "open_alert_inspected": True,
            "fraud_alert_id": None,
            "workflow_authorization": None,
        },
        "recent_transaction_index": {
            "auth-1": {
                "id": "auth-1",
                "description": "PENDING SHOP",
                "amount_cents": 4200,
                "pending": True,
            },
            "txn-1": {
                "id": "txn-1",
                "description": "POSTED SHOP",
                "amount_cents": -3500,
                "pending": False,
            },
        },
    }

    result = prepare_customer_reported_fraud_confirmation(
        disputed_authorization_ids=["auth-1"],
        disputed_transaction_ids=["txn-1"],
        issue_replacement=True,
        tool_context=SimpleNamespace(state=state),
    )

    assert result["success"] is True
    assert result["action"] == TRIAGE_CUSTOMER_REPORTED_FRAUD
    assert state["fraud_playbook"]["entry_mode"] == "CUSTOMER_REPORTED_FRAUD"
    assert state["fraud_playbook"]["workflow_authorization"]["status"] == "PREPARED"


def test_prepare_customer_reported_fraud_rejects_model_expanded_selection() -> None:
    state = {
        "session_id": "voice-session-1",
        "fraud_playbook": {
            "entry_mode": "GENERAL_SUPPORT",
            "open_alert_inspected": True,
            "fraud_alert_id": None,
        },
        "recent_transaction_index": {},
    }

    result = prepare_customer_reported_fraud_confirmation(
        disputed_authorization_ids=["invented-auth"],
        disputed_transaction_ids=[],
        issue_replacement=True,
        tool_context=SimpleNamespace(state=state),
    )

    assert result["success"] is False
    assert result["error"] == "INVALID_DISPUTED_AUTHORIZATION"


@pytest.mark.asyncio
async def test_no_alert_result_activates_catalog_guidance_and_intake_state(
    monkeypatch,
) -> None:
    events = []
    monkeypatch.setattr(agent_module, "notify_event", events.append)
    state = {
        "fraud_playbook": {
            "entry_mode": "GENERAL_SUPPORT",
            "open_alert_inspected": False,
            "fraud_alert_id": None,
        }
    }
    guidance = {
        "schema_version": 1,
        "snapshot_id": "snapshot-1",
        "source": "knowledge_catalog",
        "topic_ids": ["customer_reported_fraud"],
        "content_version": "2.1",
        "retrieved_at": "2026-07-14T00:00:00Z",
        "freshness": {"status": "FRESH"},
    }

    await after_tool_callback(
        SimpleNamespace(name="get_open_fraud_alert"),
        {},
        SimpleNamespace(state=state),
        {
            "structuredContent": {
                "success": False,
                "fraud_alert": None,
                "support_guidance": guidance,
            }
        },
    )

    assert state["fraud_playbook"]["open_alert_inspected"] is True
    assert state["support_guidance"]["snapshot_id"] == "snapshot-1"
    assert events[0]["type"] == "GUIDANCE_SNAPSHOT"


@pytest.mark.asyncio
async def test_transaction_history_result_builds_trusted_selection_index(
    monkeypatch,
) -> None:
    async def empty_account():
        return {}

    monkeypatch.setattr(agent_module, "fetch_updated_account_details", empty_account)
    state = {"fraud_playbook": {"entry_mode": "GENERAL_SUPPORT"}}

    await after_tool_callback(
        SimpleNamespace(name="get_transaction_history"),
        {},
        SimpleNamespace(state=state),
        {
            "structuredContent": {
                "success": True,
                "data": [
                    {
                        "authorization_id": "auth-1",
                        "transaction_id": None,
                        "description": "PENDING SHOP",
                        "amount_cents": 4200,
                        "pending": True,
                    },
                    {
                        "authorization_id": None,
                        "transaction_id": "txn-1",
                        "description": "POSTED SHOP",
                        "amount_cents": -3500,
                        "pending": False,
                    },
                ],
            }
        },
    )

    assert state["recent_transaction_index"]["auth-1"]["pending"] is True
    assert state["recent_transaction_index"]["txn-1"]["amount_cents"] == -3500


@pytest.mark.asyncio
async def test_wallet_commit_error_preserves_idempotent_retry_authorization() -> None:
    proposal = create_pending_proposal(
        proposal_id="wallet-proposal",
        action_type="PROVISION_GOOGLE_WALLET",
        contract_version="wallet-provisioning.v1",
        originating_customer_turn_id="customer-origin",
    )
    proposal.update(
        {
            "evidence_state": COMMIT_IN_FLIGHT,
            "presentation_turn_id": "agent-offer",
            "confirmation_turn_id": "customer-confirmation",
        }
    )
    state = {
        "fraud_playbook": {
            "pending_proposal": proposal,
        }
    }

    await after_tool_callback(
        SimpleNamespace(name="commit_wallet_provisioning"),
        {"proposal_id": "wallet-proposal"},
        SimpleNamespace(state=state),
        {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": "Unexpected keyword argument: session_id",
                }
            ],
        },
    )

    recovered = state["fraud_playbook"]["pending_proposal"]
    assert recovered["evidence_state"] == "COMMIT_RETRY"
    assert recovered["recovery_reason"] == (
        "TOOL_RESULT_NOT_SUCCESSFUL:commit_wallet_provisioning"
    )
