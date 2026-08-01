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

from agent import agent
from agent.closeout import (
    closeout_block_reason,
    mark_action_completed_for_closeout,
)
from agent.workflow_authorization import (
    PROVISION_GOOGLE_WALLET,
    create_workflow_authorization,
)


def test_closeout_requires_a_later_turn_after_completed_action() -> None:
    boundary = mark_action_completed_for_closeout(
        originating_customer_event_id="customer-action-turn",
        now_epoch_s=10,
    )

    assert (
        closeout_block_reason(
            closeout_boundary=boundary,
            workflow_authorization={"status": "COMPLETED"},
            latest_customer_turn={
                "event_id": "customer-action-turn",
                "observed_at_epoch_s": 10,
            },
        )
        == "LATER_CLOSEOUT_CUSTOMER_TURN_REQUIRED"
    )
    assert (
        closeout_block_reason(
            closeout_boundary=boundary,
            workflow_authorization={"status": "COMPLETED"},
            latest_customer_turn={
                "event_id": "customer-closeout-turn",
                "observed_at_epoch_s": 11,
            },
        )
        is None
    )


def test_closeout_never_interprets_customer_transcript() -> None:
    boundary = mark_action_completed_for_closeout(
        originating_customer_event_id="customer-action-turn",
        now_epoch_s=10,
    )
    # The runtime accepts protected event provenance only. Whether this later
    # turn means "continue" or "finish" is the model's typed end-tool choice.
    latest_turn = {
        "event_id": "customer-next-turn",
        "observed_at_epoch_s": 11,
        "transcript": "This field must never be inspected by the gate.",
    }
    assert (
        closeout_block_reason(
            closeout_boundary=boundary,
            workflow_authorization={"status": "COMPLETED"},
            latest_customer_turn=latest_turn,
        )
        is None
    )


def test_unresolved_authorization_blocks_closeout() -> None:
    authorization = create_workflow_authorization(
        action=PROVISION_GOOGLE_WALLET,
        payload={},
        session_id="session-1",
    )

    assert (
        closeout_block_reason(
            closeout_boundary=mark_action_completed_for_closeout(
                originating_customer_event_id="customer-action-turn",
                now_epoch_s=10,
            ),
            workflow_authorization=authorization,
            latest_customer_turn={
                "event_id": "customer-closeout-turn",
                "observed_at_epoch_s": 11,
            },
        )
        == "WORKFLOW_AUTHORIZATION_PREPARED"
    )


def test_commit_recovery_blocks_closeout() -> None:
    assert (
        closeout_block_reason(
            closeout_boundary=mark_action_completed_for_closeout(
                originating_customer_event_id="customer-action-turn",
                now_epoch_s=10,
            ),
            workflow_authorization={"status": "RECOVERY_REQUIRED"},
            latest_customer_turn={
                "event_id": "customer-closeout-turn",
                "observed_at_epoch_s": 11,
            },
        )
        == "WORKFLOW_AUTHORIZATION_RECOVERY_REQUIRED"
    )


@pytest.mark.asyncio
async def test_successful_action_establishes_closeout_boundary(
    monkeypatch,
) -> None:
    async def account_details():
        return {}

    monkeypatch.setattr(agent, "fetch_updated_account_details", account_details)
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    context = SimpleNamespace(
        state={
            "session_id": "session-1",
            "_voice_tool_started_at": {},
            "fraud_playbook": {
                "completion_status": "ACTIVE",
            },
        }
    )
    try:
        agent.record_customer_turn("The action is complete.")
        action_turn = (agent.latest_customer_turn_var.get() or {}).get("latest") or {}
        authorization = create_workflow_authorization(
            action=PROVISION_GOOGLE_WALLET,
            payload={},
            session_id="session-1",
        )
        authorization.update(
            {
                "status": "EXECUTING",
                "customer_event_id": action_turn.get("event_id"),
            }
        )
        context.state["fraud_playbook"]["workflow_authorization"] = authorization

        await agent.after_tool_callback(
            SimpleNamespace(name="commit_wallet_provisioning"),
            {"proposal_id": "11111111-1111-4111-8111-111111111111"},
            context,
            {
                "structuredContent": {
                    "success": True,
                    "wallet_provisioning_status": "QUEUED",
                }
            },
        )

        boundary = context.state["closeout_boundary"]
        assert boundary["originating_customer_event_id"] == action_turn["event_id"]
        assert context.state["fraud_playbook"]["workflow_authorization"][
            "status"
        ] == "COMPLETED"

        blocked = await agent.before_tool_callback(
            SimpleNamespace(name="end_consultation"), {}, context
        )
        assert blocked["status"] == "SESSION_CLOSE_CONFIRMATION_REQUIRED"

        agent.record_customer_turn("A later customer turn.")
        allowed = await agent.before_tool_callback(
            SimpleNamespace(name="end_consultation"), {}, context
        )
        assert allowed is None

        result = agent.end_consultation()
        assert result["status"] == "SUCCESS"
        assert agent.is_session_end_requested() is True
    finally:
        agent.reset_session_context(tokens)


@pytest.mark.asyncio
async def test_end_tool_uses_model_intent_for_session_without_completed_action() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    context = SimpleNamespace(
        state={
            "session_id": "session-1",
            "fraud_playbook": {"completion_status": "ACTIVE"},
        }
    )
    try:
        agent.record_customer_turn("A customer turn interpreted by the model.")
        allowed = await agent.before_tool_callback(
            SimpleNamespace(name="end_consultation"), {}, context
        )
        assert allowed is None
    finally:
        agent.reset_session_context(tokens)
