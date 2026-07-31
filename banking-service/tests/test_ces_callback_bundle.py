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

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


AGENT_DIR = (
    Path(__file__).resolve().parents[2]
    / "gecx"
    / "Credit_Support_Voice_Agent"
    / "agents"
    / "Credit_Card_Support_Agent"
)
APP_DIR = AGENT_DIR.parents[1]


def _load(relative_path: str):
    path = AGENT_DIR / relative_path
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Part:
    def __init__(self, text):
        self.text = text

    def text_or_transcript(self):
        return self.text


class Context:
    def __init__(self, *, invocation_id="turn-2", variables=None, user_text="yes"):
        self.invocation_id = invocation_id
        self.variables = variables if variables is not None else {}
        self._user_parts = [Part(user_text)] if user_text is not None else []

    def get_last_user_input(self):
        return self._user_parts


def test_voice_bundle_has_no_transcript_confirmation_classifier():
    callback = AGENT_DIR / "before_model_callbacks" / "classify_confirmation.py"
    agent = yaml.safe_load((AGENT_DIR / "Credit_Card_Support_Agent.yaml").read_text())

    assert not callback.exists()
    assert "beforeModelCallbacks" not in agent


def test_before_tool_blocks_missing_or_mismatched_confirmation():
    callback = _load("before_tool_callbacks/enforce_proposal_context.py")
    variables = {
        "proposal_id": "proposal-1",
        "proposal_action_type": "TRIAGE_FRAUD_CASE",
        "proposal_originating_turn_id": "turn-1",
        "proposal_presentation_turn_id": "turn-1",
    }
    tool = SimpleNamespace(name="banking_service_mcp_toolset.commit_fraud_triage")

    blocked = callback.before_tool_callback(
        tool, {"proposal_id": "attacker-value"}, Context(variables=variables)
    )
    assert blocked["error"] == "PROTECTED_CONFIRMATION_REQUIRED"

    allowed = callback.before_tool_callback(
        tool, {"proposal_id": "proposal-1"}, Context(variables=variables)
    )
    assert allowed is None
    assert variables["customer_turn_id"] == "turn-2"


@pytest.mark.parametrize(
    ("propose_tool", "commit_tool", "action_type"),
    (
        ("propose_fraud_triage", "commit_fraud_triage", "TRIAGE_FRAUD_CASE"),
        ("propose_card_reissue", "commit_card_reissue", "REISSUE_CARD"),
        (
            "propose_wallet_provisioning",
            "commit_wallet_provisioning",
            "PROVISION_GOOGLE_WALLET",
        ),
    ),
)
def test_ces_uses_one_typed_gate_for_all_action_proposals(
    propose_tool, commit_tool, action_type
):
    callback = _load("before_tool_callbacks/enforce_proposal_context.py")
    variables = {}
    callback.before_tool_callback(
        SimpleNamespace(name=f"banking_service_mcp_toolset.{propose_tool}"),
        {},
        Context(invocation_id="turn-1", variables=variables),
    )
    variables.update(
        {
            "proposal_id": "proposal-1",
            "proposal_presentation_turn_id": "turn-1",
        }
    )

    assert variables["proposal_action_type"] == action_type
    assert (
        callback.before_tool_callback(
            SimpleNamespace(name=f"banking_service_mcp_toolset.{commit_tool}"),
            {"proposal_id": "proposal-1"},
            Context(invocation_id="turn-2", variables=variables),
        )
        is None
    )
    assert variables["proposal_confirmation_source"] == "MODEL_TOOL_INTENT"


@pytest.mark.parametrize("decision", ("DECLINE", "REVISE", "CANCEL"))
def test_ces_non_commit_decisions_use_the_same_typed_later_turn_gate(decision):
    callback = _load("before_tool_callbacks/enforce_proposal_context.py")
    variables = {
        "proposal_id": "proposal-1",
        "proposal_action_type": "TRIAGE_FRAUD_CASE",
        "proposal_originating_turn_id": "turn-1",
        "proposal_presentation_turn_id": "turn-1",
    }
    tool = SimpleNamespace(
        name="banking_service_mcp_toolset.decide_action_proposal"
    )

    assert (
        callback.before_tool_callback(
            tool,
            {"decision": decision},
            Context(invocation_id="turn-2", variables=variables),
        )
        is None
    )
    assert variables["proposal_confirmation_source"] == "MODEL_TOOL_INTENT"
    assert variables["proposal_confirmation_turn_id"] == "turn-2"

    blocked = callback.before_tool_callback(
        tool,
        {"decision": decision},
        Context(invocation_id="turn-1", variables=variables),
    )
    assert blocked["error"] == "PROTECTED_DECISION_REQUIRED"


def test_ces_successful_non_commit_decision_clears_current_proposal():
    capture = _load("after_tool_callbacks/capture_proposal.py")
    variables = {
        "proposal_id": "proposal-1",
        "proposal_action_type": "TRIAGE_FRAUD_CASE",
        "proposal_originating_turn_id": "turn-1",
        "proposal_presentation_turn_id": "turn-1",
        "proposal_confirmation_turn_id": "turn-2",
        "proposal_confirmation_method": "EXPLICIT_VERBAL",
        "proposal_confirmation_source": "MODEL_TOOL_INTENT",
    }

    capture.after_tool_callback(
        SimpleNamespace(
            name="banking_service_mcp_toolset.decide_action_proposal"
        ),
        {"decision": "REVISE"},
        Context(invocation_id="turn-2", variables=variables),
        {
            "output": {
                "success": True,
                "status": "INVALIDATED",
                "action_type": "TRIAGE_FRAUD_CASE",
                "decision": "REVISE",
            }
        },
    )

    assert variables["proposal_id"] == ""
    assert variables["proposal_action_type"] == ""
    assert variables["proposal_presentation_turn_id"] == ""
    assert variables["fraud_review_stage"] == "INVALIDATED"


@pytest.mark.parametrize(
    ("commit_tool", "action_type"),
    (
        ("commit_fraud_triage", "TRIAGE_FRAUD_CASE"),
        ("commit_card_reissue", "REISSUE_CARD"),
        ("commit_wallet_provisioning", "PROVISION_GOOGLE_WALLET"),
    ),
)
def test_ces_successful_commit_clears_current_proposal(
    commit_tool, action_type
):
    capture = _load("after_tool_callbacks/capture_proposal.py")
    callback = _load("before_tool_callbacks/enforce_proposal_context.py")
    variables = {
        "proposal_id": "proposal-1",
        "proposal_customer_safe_summary": "Confirm the action.",
        "proposal_action_type": action_type,
        "proposal_originating_turn_id": "turn-1",
        "proposal_presentation_turn_id": "turn-1",
        "proposal_confirmation_turn_id": "turn-2",
        "proposal_confirmation_method": "EXPLICIT_VERBAL",
        "proposal_confirmation_source": "MODEL_TOOL_INTENT",
        "proposal_decision_type": "COMMIT",
    }

    capture.after_tool_callback(
        SimpleNamespace(name=f"banking_service_mcp_toolset.{commit_tool}"),
        {"proposal_id": "proposal-1"},
        Context(invocation_id="turn-2", variables=variables),
        {
            "text_output": [
                {
                    "success": True,
                    "status": "COMMITTED",
                    "action_type": action_type,
                    "proposal_id": "proposal-1",
                }
            ]
        },
    )

    assert variables["proposal_id"] == ""
    assert variables["proposal_customer_safe_summary"] == ""
    assert variables["proposal_action_type"] == ""
    assert variables["proposal_originating_turn_id"] == ""
    assert variables["proposal_presentation_turn_id"] == ""
    assert variables["proposal_confirmation_turn_id"] == ""
    assert variables["proposal_confirmation_method"] == ""
    assert variables["proposal_confirmation_source"] == ""
    assert variables["proposal_decision_type"] == ""
    assert variables["completed_proposal_action_type"] == action_type
    assert variables["completed_proposal_confirmation_turn_id"] == "turn-2"
    assert (
        variables["completed_proposal_confirmation_method"]
        == "EXPLICIT_VERBAL"
    )
    assert (
        variables["completed_proposal_confirmation_source"]
        == "MODEL_TOOL_INTENT"
    )
    assert variables["completed_proposal_decision_type"] == "COMMIT"
    if commit_tool == "commit_fraud_triage":
        assert variables["fraud_review_stage"] == "COMMITTED"

    assert (
        callback.before_tool_callback(
            SimpleNamespace(
                name="banking_service_mcp_toolset.propose_wallet_provisioning"
            ),
            {},
            Context(invocation_id="turn-3", variables=variables),
        )
        is None
    )


def test_ces_failed_commit_preserves_current_proposal_for_retry():
    capture = _load("after_tool_callbacks/capture_proposal.py")
    variables = {
        "proposal_id": "proposal-1",
        "proposal_action_type": "TRIAGE_FRAUD_CASE",
        "proposal_originating_turn_id": "turn-1",
        "proposal_presentation_turn_id": "turn-1",
        "proposal_confirmation_turn_id": "turn-2",
    }

    capture.after_tool_callback(
        SimpleNamespace(
            name="banking_service_mcp_toolset.commit_fraud_triage"
        ),
        {"proposal_id": "proposal-1"},
        Context(invocation_id="turn-2", variables=variables),
        {
            "text_output": [
                {
                    "success": False,
                    "error": "TRANSIENT_FAILURE",
                }
            ]
        },
    )

    assert variables["proposal_id"] == "proposal-1"
    assert variables["proposal_action_type"] == "TRIAGE_FRAUD_CASE"
    assert variables["proposal_presentation_turn_id"] == "turn-1"


def test_ces_questions_preserve_proposal_and_revision_is_explicit():
    callback = _load("before_tool_callbacks/enforce_proposal_context.py")
    variables = {
        "proposal_id": "proposal-1",
        "proposal_action_type": "TRIAGE_FRAUD_CASE",
        "proposal_originating_turn_id": "turn-1",
        "proposal_presentation_turn_id": "turn-1",
    }

    assert (
        callback.before_tool_callback(
            SimpleNamespace(name="banking_service_mcp_toolset.get_transaction_history"),
            {},
            Context(invocation_id="turn-2", variables=variables),
        )
        is None
    )
    assert variables["proposal_id"] == "proposal-1"

    blocked = callback.before_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.review_fraud_selection"),
        {},
        Context(invocation_id="turn-2", variables=variables),
    )
    assert blocked["error"] == "PROPOSAL_REVISION_REQUIRED"
    assert variables["proposal_id"] == "proposal-1"
    closeout = callback.before_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.offer_session_closeout"),
        {},
        Context(invocation_id="turn-2", variables=variables),
    )
    assert closeout["error"] == "PROPOSAL_DECISION_REQUIRED"


def test_ces_closeout_uses_typed_offer_and_later_turn_ordering():
    callback = _load("before_tool_callbacks/enforce_proposal_context.py")
    variables = {}
    callback.before_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.offer_session_closeout"),
        {},
        Context(invocation_id="turn-1", variables=variables),
    )

    blocked = callback.before_tool_callback(
        SimpleNamespace(name="end_session"),
        {},
        Context(invocation_id="turn-1", variables=variables),
    )
    assert blocked["error"] == "CLOSEOUT_CHECKPOINT_REQUIRED"

    allowed = callback.before_tool_callback(
        SimpleNamespace(name="end_session"),
        {},
        Context(
            invocation_id="turn-2",
            variables=variables,
            user_text="The runtime must not interpret this text.",
        ),
    )
    assert allowed is None


def test_proposal_capture_and_non_generative_presentation_recording():
    capture = _load("after_tool_callbacks/capture_proposal.py")
    variables = {}
    context = Context(invocation_id="turn-1", variables=variables, user_text=None)

    capture.after_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.propose_fraud_triage"),
        {},
        context,
        {
            "output": {
                "success": True,
                "proposal_id": "proposal-1",
                "customer_safe_summary": (
                    "Confirm that you want to dispute $100.00 at Corner Market "
                    "on card ending 4242, and block the current card and issue "
                    "a replacement."
                ),
            }
        },
    )
    assert variables["proposal_id"] == "proposal-1"
    assert variables["proposal_action_type"] == "TRIAGE_FRAUD_CASE"
    assert variables["proposal_originating_turn_id"] == "turn-1"
    assert variables["proposal_presentation_turn_id"] == "turn-1"


def test_proposal_capture_supports_ces_mcp_text_output_shape():
    capture = _load("after_tool_callbacks/capture_proposal.py")
    variables = {}

    capture.after_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.propose_fraud_triage"),
        {},
        Context(invocation_id="turn-1", variables=variables, user_text=None),
        {
            "text_output": [
                {
                    "success": True,
                    "proposal_id": "proposal-ces-1",
                    "customer_safe_summary": "Confirm the selected charges.",
                }
            ]
        },
    )

    assert variables["proposal_id"] == "proposal-ces-1"
    assert variables["proposal_customer_safe_summary"] == (
        "Confirm the selected charges."
    )


def test_voice_bundle_has_safe_idle_redaction_and_mcp_references():
    app = yaml.safe_load((APP_DIR / "app.yaml").read_text())
    instruction = (AGENT_DIR / "instruction.txt").read_text()
    toolset_template = (
        APP_DIR
        / "toolsets"
        / "banking_service_mcp_toolset"
        / "banking_service_mcp_toolset.yaml.tftpl"
    ).read_text()
    toolset = yaml.safe_load(
        toolset_template.replace(
            "${banking_service_url}",
            "https://banking.example.test",
        )
    )

    assert app["modelSettings"]["model"] == "gemini-3.1-flash-live"
    assert app["audioProcessingConfig"]["inactivityTimeout"] == "300s"
    assert app["loggingSettings"]["redactionConfig"]["enableRedaction"] is True
    declared_variables = {
        declaration["name"] for declaration in app["variableDeclarations"]
    }
    assert "session_capability" in declared_variables
    assert "user_token" not in declared_variables
    assert "active_fraud_alert_id" in declared_variables
    assert "fraud_selection_pending" not in declared_variables
    assert "fraud_review_stage" in declared_variables
    assert "completed_proposal_action_type" in declared_variables
    assert "completed_proposal_confirmation_source" in declared_variables
    custom_headers = toolset["mcpToolset"]["customHeaders"]
    assert custom_headers["x-banking-session-capability"] == (
        "$context.variables.session_capability"
    )
    assert "x-forwarded-user-context" not in custom_headers
    assert "user_token" not in instruction
    assert "You own the natural spoken wording" in instruction
    assert "Do not add a preliminary selection confirmation" in instruction
    assert "ask once for confirmation" in instruction.casefold()
    assert (
        "Completing a banking action never means the consultation is finished"
        in instruction
    )
    assert "{fraud_support_guidance_summary}" in instruction
    for tool_name in (
        "get_open_fraud_alert",
        "review_fraud_selection",
        "propose_fraud_triage",
        "commit_fraud_triage",
        "propose_card_reissue",
        "commit_card_reissue",
        "propose_wallet_provisioning",
        "commit_wallet_provisioning",
        "decide_action_proposal",
        "reverse_overdraft_fee",
        "request_credit_limit_increase",
    ):
        assert f"{{@TOOL: {tool_name}}}" not in instruction

    agent = yaml.safe_load((AGENT_DIR / "Credit_Card_Support_Agent.yaml").read_text())
    assert agent["modelSettings"]["model"] == "gemini-3.1-flash-live"
    assert "beforeModelCallbacks" not in agent
    assert set(agent["toolsets"][0]["toolIds"]) == {
        "get_open_fraud_alert",
        "review_fraud_selection",
        "propose_fraud_triage",
        "commit_fraud_triage",
        "propose_card_reissue",
        "commit_card_reissue",
        "propose_wallet_provisioning",
        "commit_wallet_provisioning",
        "decide_action_proposal",
        "offer_session_closeout",
        "request_credit_limit_increase",
        "reverse_overdraft_fee",
    }
    assert set(agent["toolsets"][0]["toolIds"]).isdisjoint(
        {
            "report_lost_stolen_card",
            "issue_replacement_card_tool",
            "push_card_to_google_wallet",
            "resolve_fraud_alert",
            "triage_fraud_case",
        }
    )
    callback_paths = {
        callback["pythonCode"]
        for callback_group in (
            agent["beforeToolCallbacks"],
            agent["afterToolCallbacks"],
            agent.get("afterModelCallbacks", []),
        )
        for callback in callback_group
    }
    assert not any("sanitize_voice_output.py" in path for path in callback_paths)
    assert not any("present_commit_result.py" in path for path in callback_paths)
    assert not any("start_fraud_review.py" in path for path in callback_paths)
    assert not any("route_fraud_selection.py" in path for path in callback_paths)
