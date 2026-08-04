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
import time

import pytest

from agent import agent
from agent.proposal_evidence import (
    AWAITING_DECISION,
    AWAITING_PRESENTATION,
    COMMIT_IN_FLIGHT,
    create_pending_proposal,
    mark_proposal_presented,
)


def pending_playbook(*, issued_at: float | None = None) -> dict:
    issued_at = time.time() if issued_at is None else issued_at
    proposal = create_pending_proposal(
        proposal_id="proposal-123",
        action_type="TRIAGE_FRAUD_CASE",
        contract_version="fraud-triage.v1",
        originating_customer_turn_id="customer-origin",
    )
    proposal = mark_proposal_presented(
        proposal,
        assistant_turn_id="assistant-presentation",
        observed_at_epoch_s=issued_at + 1,
    )
    return {
        "entry_mode": "FRAUD_ALERT",
        "fraud_alert_id": "fraud-123",
        "open_alert_inspected": True,
        "triage_submitted": False,
        "resolution_completed": False,
        "pending_proposal": proposal,
    }


def context_for(playbook: dict) -> SimpleNamespace:
    return SimpleNamespace(
        state={
            "session_id": "session-1",
            "reset_generation_token": "0:1",
            "fraud_playbook": playbook,
            "fraud_context": {"fraud_alert_id": "fraud-123"},
        }
    )


@pytest.fixture
def valid_reset(monkeypatch):
    async def generation_is_valid(**kwargs):
        return True, None

    monkeypatch.setattr(agent, "validate_reset_generation", generation_is_valid)
    monkeypatch.setattr(agent, "get_auth_headers", lambda: {})


def test_raw_customer_turn_does_not_change_authorization() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    playbook = pending_playbook()
    try:
        agent.record_customer_turn(
            "Any natural-language content",
            event_id="customer-confirmation",
            observed_at_epoch_s=1002.0,
        )
    finally:
        agent.reset_session_context(tokens)

    assert playbook["pending_proposal"]["evidence_state"] == AWAITING_DECISION


@pytest.mark.asyncio
async def test_commit_tool_choice_binds_to_later_protected_customer_turn(
    valid_reset,
) -> None:
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="session-1",
    )
    context = context_for(pending_playbook())
    try:
        presented_at = context.state["fraud_playbook"]["pending_proposal"][
            "presentation_observed_at_epoch_s"
        ]
        agent.record_customer_turn(
            "The runtime records this only as turn evidence.",
            event_id="customer-confirmation",
            observed_at_epoch_s=presented_at + 1,
        )
        result = await agent.before_tool_callback(
            SimpleNamespace(name="commit_fraud_triage"),
            {"proposal_id": "proposal-123"},
            context,
        )
    finally:
        agent.set_tool_processing(False)
        agent.reset_session_context(tokens)

    assert result is None
    proposal = context.state["fraud_playbook"]["pending_proposal"]
    assert proposal["evidence_state"] == COMMIT_IN_FLIGHT
    assert proposal["confirmation_turn_id"] == "customer-confirmation"


@pytest.mark.asyncio
async def test_commit_tool_choice_on_originating_turn_is_blocked(valid_reset) -> None:
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="session-1",
    )
    context = context_for(pending_playbook())
    try:
        presented_at = context.state["fraud_playbook"]["pending_proposal"][
            "presentation_observed_at_epoch_s"
        ]
        agent.record_customer_turn(
            "The proposal-originating customer turn.",
            event_id="customer-origin",
            observed_at_epoch_s=presented_at + 1,
        )
        result = await agent.before_tool_callback(
            SimpleNamespace(name="commit_fraud_triage"),
            {"proposal_id": "proposal-123"},
            context,
        )
    finally:
        agent.reset_session_context(tokens)

    assert result["status"] == "AUTHORIZATION_REQUIRED"
    assert context.state["fraud_playbook"]["pending_proposal"]["evidence_state"] == (
        AWAITING_DECISION
    )


@pytest.mark.asyncio
async def test_commit_tool_choice_before_presentation_is_blocked(valid_reset) -> None:
    playbook = pending_playbook()
    proposal = dict(playbook["pending_proposal"])
    proposal["evidence_state"] = AWAITING_PRESENTATION
    proposal["presentation_turn_id"] = None
    proposal["presentation_observed_at_epoch_s"] = None
    playbook["pending_proposal"] = proposal
    context = context_for(playbook)
    tokens = agent.bind_session_context(
        "customer-1",
        lambda event: event,
        support_session_id="session-1",
    )
    try:
        presented_at = time.time()
        agent.record_customer_turn(
            "A later turn cannot bypass missing presentation.",
            event_id="customer-confirmation",
            observed_at_epoch_s=presented_at,
        )
        result = await agent.before_tool_callback(
            SimpleNamespace(name="commit_fraud_triage"),
            {"proposal_id": "proposal-123"},
            context,
        )
    finally:
        agent.reset_session_context(tokens)

    assert result["status"] == "AUTHORIZATION_REQUIRED"


def test_typed_ingress_id_becomes_canonical_adk_turn_id() -> None:
    tokens = agent.bind_session_context("customer-1", lambda event: event)
    try:
        agent.record_customer_turn(
            "Customer input.",
            event_id="typed-message-1",
            observed_at_epoch_s=1002.0,
            pending_ingress=True,
        )
        turn = agent.record_customer_turn(
            " customer   input. ",
            event_id="adk-event-9",
            observed_at_epoch_s=1002.1,
            consume_pending=True,
        )
    finally:
        agent.reset_session_context(tokens)

    assert turn["event_id"] == "typed-message-1"
    assert turn["runtime_event_id"] == "adk-event-9"
    assert turn["pending_ingress"] is False
