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
CLOSEOUT_AGENT_DIR = APP_DIR / "agents" / "Session_Closeout_Agent"


def _load(relative_path: str):
    path = AGENT_DIR / relative_path
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_closeout(relative_path: str):
    path = CLOSEOUT_AGENT_DIR / relative_path
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
            "proposal_action_type": action_type,
            "proposal_originating_turn_id": "turn-1",
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
    tool = SimpleNamespace(name="banking_service_mcp_toolset.decide_action_proposal")

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
        SimpleNamespace(name="banking_service_mcp_toolset.decide_action_proposal"),
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
def test_ces_successful_commit_clears_current_proposal(commit_tool, action_type):
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
    assert variables["completed_proposal_confirmation_method"] == "EXPLICIT_VERBAL"
    assert variables["completed_proposal_confirmation_source"] == "MODEL_TOOL_INTENT"
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
    gate = _load("before_tool_callbacks/enforce_proposal_context.py")
    capture = _load("after_tool_callbacks/capture_proposal.py")
    variables = {
        "proposal_id": "proposal-1",
        "proposal_action_type": "TRIAGE_FRAUD_CASE",
        "proposal_originating_turn_id": "turn-1",
        "proposal_presentation_turn_id": "turn-1",
    }

    assert (
        gate.before_tool_callback(
            SimpleNamespace(name="banking_service_mcp_toolset.commit_fraud_triage"),
            {"proposal_id": "proposal-1"},
            Context(invocation_id="turn-2", variables=variables),
        )
        is None
    )
    assert variables["proposal_commit_attempted"] is True
    original_confirmation_turn = variables["proposal_confirmation_turn_id"]

    capture.after_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.commit_fraud_triage"),
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
    assert (
        gate.before_tool_callback(
            SimpleNamespace(name="banking_service_mcp_toolset.commit_fraud_triage"),
            {"proposal_id": "proposal-1"},
            Context(invocation_id="turn-3", variables=variables, user_text=None),
        )
        is None
    )
    assert variables["proposal_confirmation_turn_id"] == original_confirmation_turn


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

    allowed = callback.before_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.review_fraud_selection"),
        {},
        Context(invocation_id="turn-2", variables=variables),
    )
    assert allowed is None
    assert variables["proposal_id"] == "proposal-1"
    closeout_callback = _load("before_tool_callbacks/enforce_closeout.py")
    closeout = closeout_callback.before_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.offer_session_closeout"),
        {},
        Context(invocation_id="turn-2", variables=variables),
    )
    assert closeout["error"] == "PROPOSAL_DECISION_REQUIRED"


def test_ces_closeout_uses_typed_offer_and_later_turn_ordering():
    offer_callback = _load("before_tool_callbacks/enforce_closeout.py")
    authorize_callback = _load_closeout(
        "before_agent_callbacks/authorize_closeout_handoff.py"
    )

    class FakePart:
        @classmethod
        def from_agent_transfer(cls, *, agent):
            return SimpleNamespace(agent_transfer=agent)

    class FakeContent:
        def __init__(self, *, parts):
            self.parts = parts

    authorize_callback.Part = FakePart
    authorize_callback.Content = FakeContent
    variables = {}
    offer_callback.before_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.offer_session_closeout"),
        {},
        Context(invocation_id="turn-1", variables=variables),
    )
    blocked_handoff = offer_callback.before_tool_callback(
        SimpleNamespace(name="transfer_to_agent"),
        {"agent_name": "Session Closeout Agent"},
        Context(invocation_id="turn-1", variables=variables),
    )
    assert blocked_handoff["error"] == "CLOSEOUT_HANDOFF_NOT_READY"

    variables = {}
    offer_callback.before_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.offer_session_closeout"),
        {},
        Context(invocation_id="turn-1", variables=variables),
    )
    # The parent validates the later customer input. The child validates the
    # persisted checkpoint without depending on callback mutation ordering.
    authorization = offer_callback.before_tool_callback(
        SimpleNamespace(name="transfer_to_agent"),
        {"agent_name": "Session Closeout Agent"},
        Context(
            invocation_id="turn-2",
            variables=variables,
            user_text="The runtime must not interpret this text.",
        ),
    )
    assert authorization == {
        "success": True,
        "status": "CLOSEOUT_HANDOFF_AUTHORIZED",
    }
    assert variables["closeout_delegation_authorized"] is True
    assert variables["closeout_checkpoint_state"] == "OFFERED"
    assert (
        authorize_callback.before_agent_callback(
            Context(
                invocation_id="turn-2",
                variables=variables,
                user_text="The runtime must not interpret this text.",
            )
        )
        is None
    )


def test_ces_closeout_handoff_accepts_later_input_without_invocation_id():
    offer_callback = _load("before_tool_callbacks/enforce_closeout.py")
    variables = {"customer_turn_id": "action-confirmation-turn"}
    assert (
        offer_callback.before_tool_callback(
            SimpleNamespace(name="banking_service_mcp_toolset.offer_session_closeout"),
            {},
            Context(
                invocation_id="",
                variables=variables,
                user_text=None,
            ),
        )
        is None
    )

    authorization = offer_callback.before_tool_callback(
        SimpleNamespace(name="transfer_to_agent"),
        {"agent_name": "Session Closeout Agent"},
        Context(
            invocation_id="",
            variables=variables,
            user_text="No further assistance is needed.",
        ),
    )
    assert authorization == {
        "success": True,
        "status": "CLOSEOUT_HANDOFF_AUTHORIZED",
    }

    assert variables["closeout_delegation_authorized"] is True
    assert variables["closeout_checkpoint_state"] == "OFFERED"
    assert variables["closeout_originating_turn_id"] == "action-confirmation-turn"


def test_ces_non_closeout_tool_consumes_open_closeout_checkpoint():
    callback = _load("before_tool_callbacks/enforce_closeout.py")
    variables = {}
    callback.before_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.offer_session_closeout"),
        {},
        Context(invocation_id="turn-1", variables=variables),
    )

    assert (
        callback.before_tool_callback(
            SimpleNamespace(name="banking_service_mcp_toolset.get_transaction_history"),
            {},
            Context(invocation_id="turn-2", variables=variables),
        )
        is None
    )
    assert variables["closeout_checkpoint_state"] == ""
    assert variables["closeout_originating_turn_id"] == ""
    assert variables["closeout_originating_input_fingerprint"] == ""


def test_ces_closeout_transfer_preserves_open_checkpoint_for_child():
    before_callback = _load("before_tool_callbacks/enforce_closeout.py")
    after_callback = _load("after_tool_callbacks/capture_proposal.py")
    variables = {}
    before_callback.before_tool_callback(
        SimpleNamespace(name="banking_service_mcp_toolset.offer_session_closeout"),
        {},
        Context(invocation_id="turn-1", variables=variables),
    )

    transfer = SimpleNamespace(name="transfer_to_agent")
    context = Context(invocation_id="turn-2", variables=variables)
    authorization = before_callback.before_tool_callback(
        transfer,
        {"agent_name": "Session Closeout Agent"},
        context,
    )
    assert authorization == {
        "success": True,
        "status": "CLOSEOUT_HANDOFF_AUTHORIZED",
    }
    after_callback.after_tool_callback(
        transfer,
        {"agent_name": "Session Closeout Agent"},
        context,
        authorization,
    )
    assert variables["closeout_checkpoint_state"] == "OFFERED"
    assert variables["closeout_originating_turn_id"] == "turn-1"
    assert variables["closeout_delegation_authorized"] is True

    # The structural second phase is allowed through without requiring the
    # original customer input a second time.
    assert (
        before_callback.before_tool_callback(
            transfer,
            {"agent_name": "Session Closeout Agent"},
            Context(
                invocation_id="turn-2-continuation",
                variables=variables,
                user_text=None,
            ),
        )
        is None
    )


def test_ces_closeout_offer_binds_turn_header_and_clears_failed_checkpoint():
    before_callback = _load("before_tool_callbacks/enforce_closeout.py")
    after_callback = _load("after_tool_callbacks/capture_proposal.py")
    variables = {}
    context = Context(invocation_id="servicing-turn", variables=variables)
    tool = SimpleNamespace(
        name="banking_service_mcp_toolset.offer_session_closeout"
    )

    assert before_callback.before_tool_callback(tool, {}, context) is None
    assert variables["customer_turn_id"] == "servicing-turn"
    assert variables["closeout_checkpoint_state"] == "OFFERED"

    assert after_callback.after_tool_callback(
        tool,
        {},
        context,
        {"status": "error", "error": "transport rejected"},
    ) is None
    assert variables["closeout_checkpoint_state"] == ""
    assert variables["closeout_originating_turn_id"] == ""
    assert variables["closeout_delegation_authorized"] is False


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
    assert "synthesizeSpeechConfigs" not in app["audioProcessingConfig"]
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
    assert "closeout_delegation_authorized" in declared_variables
    assert "closeout_end_attempted" in declared_variables
    assert "closeout_farewell_ready" not in declared_variables
    assert "closeout_playout_acknowledged" not in declared_variables
    assert "closeout_offer_required" in declared_variables
    custom_headers = toolset["mcpToolset"]["customHeaders"]
    assert custom_headers == {
        "x-banking-session-capability": "$context.variables.session_capability",
        "x-support-session-id": "$context.variables.support_session_id",
        "x-runtime-name": "$context.variables.runtime_name",
        "x-runtime-session-id": "$context.variables.runtime_session_id",
        "x-customer-turn-id": "$context.variables.customer_turn_id",
        "x-reset-generation": "$context.variables.reset_generation",
        "x-catalog-snapshot-id": "$context.variables.catalog_snapshot_id",
        "x-ces-app-id": "$context.variables.ces_app_id",
        "x-ces-version-or-deployment-id": (
            "$context.variables.ces_version_or_deployment_id"
        ),
        "x-proposal-presentation-turn-id": (
            "$context.variables.proposal_presentation_turn_id"
        ),
        "x-proposal-confirmation-turn-id": (
            "$context.variables.proposal_confirmation_turn_id"
        ),
        "x-proposal-confirmation-method": (
            "$context.variables.proposal_confirmation_method"
        ),
        "x-proposal-confirmation-source": (
            "$context.variables.proposal_confirmation_source"
        ),
    }
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
    assert agent.get("tools", []) == []
    assert agent["childAgents"] == ["Session Closeout Agent"]
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
    assert any("enforce_closeout.py" in path for path in callback_paths)
    assert any("enforce_proposal_context.py" in path for path in callback_paths)
    assert any("ensure_closeout_offer.py" in path for path in callback_paths)
    assert not any("sanitize_voice_output.py" in path for path in callback_paths)
    assert not any("present_commit_result.py" in path for path in callback_paths)
    assert not any("start_fraud_review.py" in path for path in callback_paths)
    assert not any("route_fraud_selection.py" in path for path in callback_paths)


def test_voice_bundle_isolates_native_session_end_in_closeout_agent():
    support_agent = yaml.safe_load(
        (AGENT_DIR / "Credit_Card_Support_Agent.yaml").read_text()
    )
    support_instruction = (AGENT_DIR / "instruction.txt").read_text()
    closeout_agent = yaml.safe_load(
        (CLOSEOUT_AGENT_DIR / "Session_Closeout_Agent.yaml").read_text()
    )
    closeout_instruction = (CLOSEOUT_AGENT_DIR / "instruction.txt").read_text()

    assert "end_session" not in support_agent.get("tools", [])
    assert support_agent["childAgents"] == ["Session Closeout Agent"]
    assert support_agent["transferRules"] == [
        {
            "childAgent": "Session Closeout Agent",
            "direction": "CHILD_TO_PARENT",
            "disablePlannerTransfer": {
                "expressionCondition": {
                    "expression": "closeout_delegation_authorized == true"
                }
            },
        }
    ]
    assert "{@AGENT: Session Closeout Agent}" in support_instruction
    assert "Never say goodbye yourself" in support_instruction

    assert closeout_agent["tools"] == ["end_session"]
    assert closeout_agent["toolsets"] == [
        {
            "toolset": "banking_service_mcp_toolset",
            "toolIds": ["complete_consultation"],
        }
    ]
    assert closeout_agent["modelSettings"]["model"] == "gemini-3.1-flash-live"
    assert closeout_agent["beforeAgentCallbacks"] == [
        {
            "pythonCode": (
                "agents/Session_Closeout_Agent/"
                "before_agent_callbacks/authorize_closeout_handoff.py"
            ),
            "description": (
                "Reject a closeout handoff unless trusted state proves the "
                "workflow is ready to end."
            ),
        }
    ]
    assert "beforeToolCallbacks" not in closeout_agent
    assert "beforeModelCallbacks" not in closeout_agent
    assert closeout_agent["afterModelCallbacks"] == [
        {
            "pythonCode": (
                "agents/Session_Closeout_Agent/"
                "after_model_callbacks/finalize_closeout.py"
            ),
            "description": (
                "Replace an authorized completion intent with the native "
                "end-session system call."
            ),
        }
    ]
    assert "farewell of 2 to 4 words" not in closeout_instruction
    assert "short, polite, context-neutral spoken farewell" in closeout_instruction
    assert "execute {@TOOL: complete_consultation}" in closeout_instruction
    assert "spoken text FIRST" in closeout_instruction
    assert "Never ask whether the customer needs anything else" in (
        closeout_instruction
    )
    assert "Do not assume or refer to any time of day" in closeout_instruction


def test_parent_appends_missing_closeout_offer_without_replacing_audio():
    callback = _load(
        "after_model_callbacks/ensure_closeout_offer.py"
    )

    class FakePart:
        def __init__(
            self, *, text=None, function_name=None, args=None, agent_transfer=None
        ):
            self.text = text
            self.agent_transfer = agent_transfer
            self.function_call = (
                SimpleNamespace(name=function_name, args=args or {})
                if function_name
                else None
            )

        @classmethod
        def from_function_call(cls, *, name, args):
            return cls(function_name=name, args=args)

        @classmethod
        def from_agent_transfer(cls, *, agent):
            return cls(agent_transfer=agent)

        def has_function_call(self, name):
            return bool(self.function_call and self.function_call.name == name)

    callback.Part = FakePart
    response = SimpleNamespace(
        content=SimpleNamespace(parts=[FakePart(text="Action completed.")])
    )
    result = callback.after_model_callback(
        SimpleNamespace(
            variables={
                "closeout_offer_required": True,
                "proposal_id": "",
                "proposal_commit_attempted": False,
            }
        ),
        response,
    )

    assert result is None
    assert response.content.parts[0].text == "Action completed."
    assert response.content.parts[1].function_call.name.endswith(
        "offer_session_closeout"
    )


def test_authorized_closeout_continuation_becomes_child_transfer():
    callback = _load("after_model_callbacks/ensure_closeout_offer.py")

    class FakePart:
        def __init__(self, *, text=None, agent_transfer=None):
            self.text = text
            self.agent_transfer = agent_transfer

        @classmethod
        def from_agent_transfer(cls, *, agent):
            return cls(agent_transfer=agent)

    callback.Part = FakePart
    response = SimpleNamespace(
        content=SimpleNamespace(
            parts=[FakePart(text="Is there anything else I can help you with?")]
        )
    )

    assert (
        callback.after_model_callback(
            SimpleNamespace(
                variables={"closeout_delegation_authorized": True}
            ),
            response,
        )
        is None
    )
    assert len(response.content.parts) == 1
    assert response.content.parts[0].text is None
    assert response.content.parts[0].agent_transfer == "Session Closeout Agent"


def test_closeout_agent_rejects_handoff_during_pending_proposal():
    callback = _load_closeout(
        "before_agent_callbacks/authorize_closeout_handoff.py"
    )

    class FakePart:
        @classmethod
        def from_agent_transfer(cls, *, agent):
            return SimpleNamespace(agent_transfer=agent)

    class FakeContent:
        def __init__(self, *, parts):
            self.parts = parts

    callback.Part = FakePart
    callback.Content = FakeContent
    variables = {
        "closeout_checkpoint_state": "",
        "proposal_id": "wallet-proposal",
        "proposal_commit_attempted": True,
    }

    response = callback.before_agent_callback(
        Context(invocation_id="wallet-confirmation", variables=variables)
    )

    assert response.parts[0].agent_transfer == "Credit Card Support Agent"
    assert variables["closeout_delegation_authorized"] is False
    assert variables["closeout_end_attempted"] is False


def test_closeout_completion_intent_becomes_native_end_session():
    callback = _load_closeout("after_model_callbacks/finalize_closeout.py")

    class FakePart:
        def __init__(self, *, text=None, function_name=None, args=None, end_reason=None):
            self.text = text
            self.function_call = (
                SimpleNamespace(name=function_name, args=args or {})
                if function_name
                else None
            )
            self.end_reason = end_reason

        @classmethod
        def from_end_session(cls, *, reason):
            return cls(end_reason=reason)

    callback.Part = FakePart
    variables = {
        "closeout_delegation_authorized": True,
        "closeout_checkpoint_state": "OFFERED",
        "closeout_end_attempted": False,
        "proposal_id": "",
        "proposal_commit_attempted": False,
    }
    response = SimpleNamespace(
        content=SimpleNamespace(
            parts=[
                FakePart(text="You're very welcome. Goodbye."),
                FakePart(
                    function_name=(
                        "banking_service_mcp_toolset_complete_consultation"
                    ),
                    args={"reason": "customer_query_ended"},
                ),
            ]
        )
    )

    assert (
        callback.after_model_callback(
            SimpleNamespace(variables=variables), response
        )
        is None
    )
    assert response.content.parts[0].text == "You're very welcome. Goodbye."
    assert response.content.parts[1].end_reason == "customer_query_ended"
    assert variables["closeout_checkpoint_state"] == "ENDING"
    assert variables["closeout_end_attempted"] is True


def test_closeout_completion_intent_with_wrong_reason_is_not_rewritten():
    callback = _load_closeout("after_model_callbacks/finalize_closeout.py")

    class FakePart:
        def __init__(self, *, text=None, function_name=None, args=None):
            self.text = text
            self.function_call = (
                SimpleNamespace(name=function_name, args=args or {})
                if function_name
                else None
            )

    callback.Part = FakePart
    variables = {
        "closeout_delegation_authorized": True,
        "closeout_checkpoint_state": "OFFERED",
        "closeout_end_attempted": False,
        "proposal_id": "",
        "proposal_commit_attempted": False,
    }
    wrapper = FakePart(
        function_name="banking_service_mcp_toolset_complete_consultation",
        args={"reason": "unspecified"},
    )
    response = SimpleNamespace(
        content=SimpleNamespace(
            parts=[FakePart(text="Goodbye."), wrapper]
        )
    )

    assert (
        callback.after_model_callback(
            SimpleNamespace(variables=variables), response
        )
        is None
    )
    assert response.content.parts[1] is wrapper
    assert variables["closeout_checkpoint_state"] == "OFFERED"
    assert variables["closeout_end_attempted"] is False


def test_closeout_streamed_tool_only_chunk_becomes_native_end_session():
    callback = _load_closeout("after_model_callbacks/finalize_closeout.py")

    class FakePart:
        def __init__(self, *, function_name=None, args=None, end_reason=None):
            self.function_call = (
                SimpleNamespace(name=function_name, args=args or {})
                if function_name
                else None
            )
            self.end_reason = end_reason

        @classmethod
        def from_end_session(cls, *, reason):
            return cls(end_reason=reason)

    callback.Part = FakePart
    wrapper = FakePart(
        function_name="banking_service_mcp_toolset_complete_consultation",
        args={"reason": "customer_query_ended"},
    )
    response = SimpleNamespace(content=SimpleNamespace(parts=[wrapper]))
    variables = {
        "closeout_delegation_authorized": True,
        "closeout_checkpoint_state": "OFFERED",
        "closeout_end_attempted": False,
        "proposal_id": "",
        "proposal_commit_attempted": False,
    }

    assert (
        callback.after_model_callback(
            SimpleNamespace(variables=variables), response
        )
        is None
    )
    assert response.content.parts[0].end_reason == "customer_query_ended"
    assert variables["closeout_checkpoint_state"] == "ENDING"
    assert variables["closeout_end_attempted"] is True
