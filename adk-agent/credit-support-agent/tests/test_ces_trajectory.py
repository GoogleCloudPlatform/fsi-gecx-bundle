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

from __future__ import annotations

from agent.ces_trajectory import normalize_ces_conversation, safe_conversation_identity
from agent.trajectory_eval import TrajectoryExpectation, evaluate_trajectory


def _chunk(role: str, timestamp: str, **chunk: object) -> dict[str, object]:
    return {
        "role": role,
        "eventTime": timestamp,
        "chunks": [chunk],
    }


def _conversation(*, include_end: bool = True) -> dict[str, object]:
    messages = [
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:00Z",
            updatedVariables={
                "runtime_name": "CES_GEMINI_LIVE",
                "reset_generation": "[REDACTED]",
            },
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:01Z",
            toolCall={"toolsetTool": {"toolId": "get_open_fraud_alert"}, "args": {}},
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:02Z",
            toolResponse={
                "toolsetTool": {"toolId": "get_open_fraud_alert"},
                "response": {
                    "text_output": [
                        {
                            "success": True,
                            "support_guidance": {
                                "source": "knowledge_catalog",
                                "topic_ids": ["fraud_golden_path"],
                                "snapshot_id": "snapshot-1",
                                "content_version": "2.5",
                            },
                        }
                    ]
                },
            },
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:03Z",
            transcript="Do you recognize these transactions?",
        ),
        _chunk("user", "2026-07-27T03:39:04Z", transcript="No, I don't."),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:05Z",
            updatedVariables={
                "fraud_review_stage": "AWAITING_ACTION_CONFIRMATION",
                "fraud_review_ready": True,
            },
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:05Z",
            toolCall={
                "toolsetTool": {"toolId": "propose_fraud_triage"},
                "args": {"proposal_secret": "must-not-survive"},
            },
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:06Z",
            toolResponse={
                "toolsetTool": {"toolId": "propose_fraud_triage"},
                "response": {
                    "text_output": [
                        {
                            "success": True,
                            "status": "PROPOSED",
                            "contract_version": "fraud-triage.v1",
                            "proposal_id": "must-not-survive",
                        }
                    ]
                },
            },
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:07Z",
            updatedVariables={"proposal_presentation_turn_id": "turn-secret"},
        ),
        _chunk("user", "2026-07-27T03:39:08Z", transcript="Yes, I confirm."),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:09Z",
            updatedVariables={
                "completed_proposal_action_type": "TRIAGE_FRAUD_CASE",
                "completed_proposal_confirmation_source": "MODEL_TOOL_INTENT",
                "completed_proposal_confirmation_turn_id": "turn-secret",
                "completed_proposal_decision_type": "COMMIT",
            },
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:10Z",
            toolCall={
                "toolsetTool": {"toolId": "commit_fraud_triage"},
                "args": {"proposal_id": "must-not-survive"},
            },
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:11Z",
            toolResponse={
                "toolsetTool": {"toolId": "commit_fraud_triage"},
                "response": {
                    "text_output": [
                        {
                            "success": True,
                            "status": "COMMITTED",
                            "contract_version": "fraud-triage.v1",
                            "outcome": "PENDING_SPECIALIST_REVIEW",
                        }
                    ]
                },
            },
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:12Z",
            updatedVariables={
                "fraud_review_stage": "COMMITTED",
            },
        ),
    ]
    if include_end:
        messages.extend(
            [
                _chunk(
                "Credit Card Support Agent",
                "2026-07-27T03:39:13Z",
                toolCall={
                    "tool": "projects/example/locations/us/apps/app/tools/end_session",
                    "args": {},
                },
                ),
                _chunk(
                    "Credit Card Support Agent",
                    "2026-07-27T03:39:13Z",
                    toolResponse={
                        "tool": (
                            "projects/example/locations/us/apps/app/tools/end_session"
                        ),
                        "response": {"text_output": []},
                    },
                ),
            ]
        )
    return {
        "name": "projects/example/locations/us/apps/app/conversations/conversation-1",
        "source": "LIVE",
        "startTime": "2026-07-27T03:39:00Z",
        "endTime": "2026-07-27T03:39:14Z",
        "turnCount": 3,
        "channelType": "BIDI_STREAMING",
        "languageCode": "en-US",
        "appVersion": "projects/example/locations/us/apps/app/versions/version-1",
        "deployment": "projects/example/locations/us/apps/app/deployments/deployment-1",
        "turns": [{"messages": messages, "rootSpan": {}}],
    }


def _expectation() -> TrajectoryExpectation:
    return TrajectoryExpectation(
        required_tools={
            "get_open_fraud_alert": 1,
            "propose_fraud_triage": 1,
            "commit_fraud_triage": 1,
        },
        required_proposal_outcomes=(
            "PROPOSED",
            "PRESENTED",
            "CONFIRMED",
            "COMMITTED",
        ),
        expected_banking_outcome="PENDING_SPECIALIST_REVIEW",
        require_direct_selection_to_proposal=True,
        required_review_stages=("AWAITING_ACTION_CONFIRMATION", "COMMITTED"),
        require_ready_review_before_proposal=True,
        expected_runtime_name="CES_GEMINI_LIVE",
        require_runtime_version=True,
        require_catalog_identity=True,
        required_contract_version="fraud-triage.v1",
    )


def test_normalized_ces_golden_trajectory_passes_shared_evaluator() -> None:
    events = normalize_ces_conversation(_conversation())

    result = evaluate_trajectory(events, _expectation())

    assert result.passed is True
    assert result.metrics["runtime_name"] == "CES_GEMINI_LIVE"
    assert result.metrics["catalog_snapshot_id"] == "snapshot-1"
    assert result.metrics["banking_outcome"] == "PENDING_SPECIALIST_REVIEW"
    assert result.metrics["proposal_outcomes"] == [
        "PROPOSED",
        "PRESENTED",
        "CONFIRMED",
        "COMMITTED",
    ]


def test_completed_confirmation_evidence_survives_ces_delta_updates() -> None:
    conversation = _conversation()
    messages = conversation["turns"][0]["messages"]
    messages.extend(
        [
            _chunk(
                "Credit Card Support Agent",
                "2026-07-27T03:39:12Z",
                updatedVariables={
                    "completed_proposal_action_type": "PROVISION_GOOGLE_WALLET",
                    "completed_proposal_confirmation_turn_id": "wallet-turn",
                },
            ),
            _chunk(
                "Credit Card Support Agent",
                "2026-07-27T03:39:12Z",
                toolCall={
                    "toolsetTool": {"toolId": "commit_wallet_provisioning"},
                    "args": {},
                },
            ),
            _chunk(
                "Credit Card Support Agent",
                "2026-07-27T03:39:12Z",
                toolResponse={
                    "toolsetTool": {"toolId": "commit_wallet_provisioning"},
                    "response": {
                        "text_output": [
                            {
                                "success": True,
                                "status": "COMMITTED",
                                "action_type": "PROVISION_GOOGLE_WALLET",
                            }
                        ]
                    },
                },
            ),
        ]
    )

    events = normalize_ces_conversation(conversation)

    confirmations = [
        event
        for event in events
        if event.get("type") == "ACTION_PROPOSAL"
        and event.get("outcome") == "CONFIRMED"
    ]
    assert [event["action_type"] for event in confirmations] == [
        "TRIAGE_FRAUD_CASE",
        "PROVISION_GOOGLE_WALLET",
    ]


def test_normalizer_does_not_retain_tool_arguments_or_protected_ids() -> None:
    events = normalize_ces_conversation(_conversation())

    rendered = repr(events)

    assert "must-not-survive" not in rendered
    assert "turn-secret" not in rendered
    assert all("args" not in event for event in events)


def test_missing_end_session_is_an_unexpected_disconnect() -> None:
    events = normalize_ces_conversation(_conversation(include_end=False))

    result = evaluate_trajectory(events, _expectation())

    assert result.passed is False
    assert "Unexpected terminal outcome UNEXPECTED_DISCONNECT." in result.failures


def test_typed_decline_normalizes_without_false_confirmation() -> None:
    conversation = _conversation()
    messages = conversation["turns"][0]["messages"]
    conversation["turns"][0]["messages"] = [
        *messages[:9],
        _chunk("user", "2026-07-27T03:39:08Z", transcript="Do not proceed."),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:09Z",
            updatedVariables={
                "proposal_confirmation_source": "MODEL_TOOL_INTENT",
                "proposal_decision_type": "DECLINE",
            },
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:10Z",
            toolCall={
                "toolsetTool": {"toolId": "decide_action_proposal"},
                "args": {"decision": "DECLINE"},
            },
        ),
        _chunk(
            "Credit Card Support Agent",
            "2026-07-27T03:39:11Z",
            toolResponse={
                "toolsetTool": {"toolId": "decide_action_proposal"},
                "response": {
                    "text_output": [
                        {
                            "success": True,
                            "status": "DECLINED",
                            "action_type": "TRIAGE_FRAUD_CASE",
                            "contract_version": "fraud-triage.v1",
                            "decision": "DECLINE",
                            "invalidation_reason": "CUSTOMER_DECLINED",
                        }
                    ]
                },
            },
        ),
            *messages[-2:],
    ]

    events = normalize_ces_conversation(conversation)
    result = evaluate_trajectory(
        events,
        TrajectoryExpectation(
            required_tools={
                "get_open_fraud_alert": 1,
                "propose_fraud_triage": 1,
                "decide_action_proposal": 1,
            },
            forbidden_tools=("commit_fraud_triage",),
            required_proposal_outcomes=("PROPOSED", "PRESENTED", "DECLINED"),
            forbidden_proposal_outcomes=("CONFIRMED", "COMMITTED"),
            expected_runtime_name="CES_GEMINI_LIVE",
            require_runtime_version=True,
            require_catalog_identity=True,
            required_contract_version="fraud-triage.v1",
        ),
    )

    assert result.passed is True
    assert result.metrics["proposal_outcomes"] == [
        "PROPOSED",
        "PRESENTED",
        "DECLINED",
    ]


def test_safe_identity_contains_only_resource_provenance() -> None:
    conversation = _conversation()
    conversation["session_capability"] = "secret"
    conversation["customer_id"] = "customer-secret"

    identity = safe_conversation_identity(conversation)

    assert identity["app_version"].endswith("/version-1")
    assert "session_capability" not in identity
    assert "customer_id" not in identity
