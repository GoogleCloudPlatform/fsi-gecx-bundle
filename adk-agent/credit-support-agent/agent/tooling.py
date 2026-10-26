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

"""ADK tool adapters used by the Live voice agent."""

from __future__ import annotations

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool import McpToolset
from google.genai import types

RETIRED_MCP_TOOLS = frozenset(
    {
        "report_lost_stolen_card",
        "issue_replacement_card_tool",
        "push_card_to_google_wallet",
        "resolve_fraud_alert",
        "triage_fraud_case",
    }
)

ADK_BANKING_MCP_TOOL_ALLOWLIST = frozenset(
    {
        "unfreeze_card",
        "get_open_fraud_alert",
        "review_fraud_selection",
        "discover_playbooks",
        "record_playbook_decision",
        "prepare_action_proposal",
        "commit_action_proposal",
        "decide_action_proposal",
        "triage_customer_reported_fraud",
        "reverse_overdraft_fee",
        "get_transaction_history",
    }
)

ADK_RUNTIME_TOOL_NAMES = frozenset(
    {
        "prepare_customer_reported_fraud_confirmation",
        "set_conversation_language",
        "end_consultation",
        "transfer_to_human",
    }
)

if not ADK_BANKING_MCP_TOOL_ALLOWLIST.isdisjoint(ADK_RUNTIME_TOOL_NAMES):
    raise RuntimeError("ADK banking MCP and runtime-local tool names must be unique.")

# Tools whose results change proposal, authorization, or banking state. Gemini
# 3.x Live defaults to asynchronous (NON_BLOCKING) calls and may issue several
# at once; these must run synchronously and one at a time.
ORDERED_TOOL_NAMES = frozenset(
    {
        "record_playbook_decision",
        "prepare_action_proposal",
        "commit_action_proposal",
        "decide_action_proposal",
        "triage_customer_reported_fraud",
        "reverse_overdraft_fee",
        "unfreeze_card",
        "prepare_customer_reported_fraud_confirmation",
        "set_conversation_language",
    }
)

# Results added to context without prompting another model turn. The handoff
# path speaks before the call; end_consultation stays audible because its
# closeout-block result carries a customer-facing prompt.
SILENT_RESPONSE_TOOL_NAMES = frozenset({"transfer_to_human"})

if not ORDERED_TOOL_NAMES <= (ADK_BANKING_MCP_TOOL_ALLOWLIST | ADK_RUNTIME_TOOL_NAMES):
    raise RuntimeError("Ordered Live tools must be exposed ADK tools.")


def project_adk_banking_tools(tools: list[BaseTool]) -> list[BaseTool]:
    """Return only the reviewed banking capabilities exposed to ADK."""
    return [
        tool for tool in tools if tool.name in ADK_BANKING_MCP_TOOL_ALLOWLIST
    ]


class LiveMcpToolset(McpToolset):
    """Apply one explicit Live response policy to dynamically loaded MCP tools."""

    async def get_tools(
        self,
        readonly_context: ReadonlyContext | None = None,
    ) -> list[BaseTool]:
        tools = project_adk_banking_tools(
            await super().get_tools(readonly_context)
        )
        mode = (readonly_context.state.get("mode") if readonly_context else None)
        scheduling = (
            types.FunctionResponseScheduling.INTERRUPT
            if mode == "video"
            else types.FunctionResponseScheduling.WHEN_IDLE
        )
        for tool in tools:
            configure_live_tool(tool, response_scheduling=scheduling)
        return tools


def configure_live_tool(
    tool: BaseTool,
    *,
    response_scheduling: types.FunctionResponseScheduling = types.FunctionResponseScheduling.WHEN_IDLE,
) -> BaseTool:
    """Apply the voice agent's ADK 2.4 function-response policy.

    Ordered tools are declared BLOCKING with no response scheduling: ADK 2.4
    marks every tool that has a ``response_scheduling`` as NON_BLOCKING, and
    the Live API applies scheduling only to NON_BLOCKING calls. BLOCKING is
    also the 2.5 default, so the rollback model keeps its proven semantics.
    """
    if tool.name in ORDERED_TOOL_NAMES:
        tool.response_scheduling = None
        _declare_blocking(tool)
        return tool
    if tool.name in SILENT_RESPONSE_TOOL_NAMES:
        tool.response_scheduling = types.FunctionResponseScheduling.SILENT
        return tool
    # Audio remains on the proven idle policy. Preview Avatar sessions receive
    # read results immediately so a blocked response cannot remain queued
    # behind a later successful retry and be narrated out of order.
    tool.response_scheduling = response_scheduling
    return tool


def _declare_blocking(tool: BaseTool) -> None:
    if getattr(tool, "_live_blocking_declaration", False):
        return
    build_declaration = tool._get_declaration

    def blocking_declaration():
        declaration = build_declaration()
        if declaration is not None:
            declaration.behavior = types.Behavior.BLOCKING
        return declaration

    tool._get_declaration = blocking_declaration
    tool._live_blocking_declaration = True

