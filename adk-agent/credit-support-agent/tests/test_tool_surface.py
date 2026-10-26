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
from google.adk.flows.llm_flows import base_llm_flow, functions
from google.adk.models.llm_request import LlmRequest
from google.adk.tools.base_tool import BaseTool
from google.genai import types

from agent import agent
from agent.tooling import (
    ADK_BANKING_MCP_TOOL_ALLOWLIST,
    ADK_RUNTIME_TOOL_NAMES,
    ORDERED_TOOL_NAMES,
    RETIRED_MCP_TOOLS,
    configure_live_tool,
    project_adk_banking_tools,
)


def test_adk_banking_tool_projection_is_an_explicit_allowlist() -> None:
    advertised = [
        SimpleNamespace(name="get_open_fraud_alert"),
        SimpleNamespace(name="end_consultation"),
        SimpleNamespace(name="push_card_to_google_wallet"),
        SimpleNamespace(name="unexpected_future_tool"),
    ]

    projected = project_adk_banking_tools(advertised)

    assert [tool.name for tool in projected] == ["get_open_fraud_alert"]


def test_adk_banking_and_runtime_tool_names_are_unique() -> None:
    assert ADK_BANKING_MCP_TOOL_ALLOWLIST.isdisjoint(ADK_RUNTIME_TOOL_NAMES)
    assert "end_consultation" in ADK_RUNTIME_TOOL_NAMES
    assert "offer_session_closeout" not in ADK_RUNTIME_TOOL_NAMES
    assert ADK_BANKING_MCP_TOOL_ALLOWLIST.isdisjoint(RETIRED_MCP_TOOLS)


def test_catalog_actions_share_one_model_visible_discovery_and_lifecycle_surface():
    assert {"discover_playbooks", "prepare_action_proposal", "commit_action_proposal"} <= ADK_BANKING_MCP_TOOL_ALLOWLIST
    assert ADK_BANKING_MCP_TOOL_ALLOWLIST.isdisjoint({
        "propose_fraud_triage", "commit_fraud_triage", "propose_card_reissue",
        "commit_card_reissue", "propose_wallet_provisioning", "commit_wallet_provisioning",
    })


def _live_declarations(tools) -> dict:
    """Run ADK 2.4's Live declaration pass exactly as a run_live request does."""
    request = LlmRequest()
    request.append_tools(list(tools))
    base_llm_flow._mark_live_async_tools_non_blocking(request)
    return {
        declaration.name: declaration
        for tool in request.config.tools
        for declaration in tool.function_declarations or []
    }


class NamedTool(BaseTool):
    def __init__(self, name: str) -> None:
        super().__init__(name=name, description=name)

    def _get_declaration(self):
        return types.FunctionDeclaration(name=self.name, description=self.name)


@pytest.mark.parametrize(
    "scheduling",
    [types.FunctionResponseScheduling.WHEN_IDLE, types.FunctionResponseScheduling.INTERRUPT],
)
def test_ordered_tools_are_blocking_and_read_tools_stay_asynchronous(scheduling) -> None:
    tools = [
        configure_live_tool(NamedTool(name), response_scheduling=scheduling)
        for name in sorted(ADK_BANKING_MCP_TOOL_ALLOWLIST)
    ]

    declarations = _live_declarations(tools)

    for tool in tools:
        if tool.name in ORDERED_TOOL_NAMES:
            assert tool.response_scheduling is None, tool.name
            assert declarations[tool.name].behavior is types.Behavior.BLOCKING, tool.name
        else:
            assert tool.response_scheduling is scheduling, tool.name
            assert declarations[tool.name].behavior is types.Behavior.NON_BLOCKING, tool.name


def test_required_money_path_tools_are_ordered() -> None:
    assert {
        "record_playbook_decision",
        "prepare_action_proposal",
        "commit_action_proposal",
        "decide_action_proposal",
        "triage_customer_reported_fraud",
        "reverse_overdraft_fee",
        "unfreeze_card",
        "prepare_customer_reported_fraud_confirmation",
        "set_conversation_language",
    } <= ORDERED_TOOL_NAMES


def test_runtime_tool_policy_silences_only_the_handoff() -> None:
    tools = {tool.name: tool for tool in agent.create_runtime_tools()}

    declarations = _live_declarations(tools.values())

    assert set(tools) == ADK_RUNTIME_TOOL_NAMES
    silent = {
        name
        for name, tool in tools.items()
        if tool.response_scheduling is types.FunctionResponseScheduling.SILENT
    }
    assert silent == {"transfer_to_human"}
    assert declarations["set_conversation_language"].behavior is types.Behavior.BLOCKING
    assert (
        declarations["prepare_customer_reported_fraud_confirmation"].behavior
        is types.Behavior.BLOCKING
    )


def test_end_consultation_closeout_block_is_not_silent() -> None:
    end_consultation = next(
        tool for tool in agent.create_runtime_tools() if tool.name == "end_consultation"
    )
    blocked = {
        "success": False,
        "status": "SESSION_CLOSE_CONFIRMATION_REQUIRED",
        "customer_response": "Is there anything else I can help you with?",
    }

    content = functions._build_function_response_content(end_consultation, blocked, "call-1")

    scheduling = content.parts[0].function_response.scheduling
    assert scheduling is not types.FunctionResponseScheduling.SILENT


@pytest.mark.asyncio
async def test_end_consultation_success_is_silent_and_blocked_resets_to_audible() -> None:
    end_consultation = next(
        tool for tool in agent.create_runtime_tools() if tool.name == "end_consultation"
    )
    tool_context = SimpleNamespace(state={"fraud_playbook": {}})
    succeeded = {
        "status": "SUCCESS",
        "retryable": False,
        "message": "Session end signal sent.",
    }

    await agent.after_tool_callback(
        end_consultation, {}, tool_context, succeeded
    )
    success_content = functions._build_function_response_content(
        end_consultation, succeeded, "call-success"
    )
    assert (
        success_content.parts[0].function_response.scheduling
        is types.FunctionResponseScheduling.SILENT
    )

    blocked = {
        "success": False,
        "status": "SESSION_CLOSE_CONFIRMATION_REQUIRED",
        "customer_response": "Is there anything else I can help you with?",
    }
    await agent.after_tool_callback(
        end_consultation, {}, tool_context, blocked
    )
    blocked_content = functions._build_function_response_content(
        end_consultation, blocked, "call-blocked"
    )
    assert (
        blocked_content.parts[0].function_response.scheduling
        is not types.FunctionResponseScheduling.SILENT
    )


def test_voice_agent_sends_no_thinking_configuration() -> None:
    voice_agent = agent.create_voice_agent(model="gemini-3.8-live")

    assert voice_agent.planner is None
    assert voice_agent.generate_content_config is None
