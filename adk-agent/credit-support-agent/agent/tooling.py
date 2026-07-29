"""ADK tool adapters used by the Live voice agent."""

from __future__ import annotations

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool import McpToolset
from google.genai import types

LEGACY_DIRECT_ACTION_TOOLS = {
    "report_lost_stolen_card",
    "issue_replacement_card_tool",
    "push_card_to_google_wallet",
    "triage_fraud_case",
}


class LiveMcpToolset(McpToolset):
    """Apply one explicit Live response policy to dynamically loaded MCP tools."""

    async def get_tools(
        self,
        readonly_context: ReadonlyContext | None = None,
    ) -> list[BaseTool]:
        tools = [
            tool
            for tool in await super().get_tools(readonly_context)
            if tool.name not in LEGACY_DIRECT_ACTION_TOOLS
        ]
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
    """Apply the voice agent's ADK 2.4 function-response policy."""
    # Audio remains on the proven idle policy. Preview Avatar sessions receive
    # results immediately so a blocked response cannot remain queued behind a
    # later successful retry and be narrated out of order.
    tool.response_scheduling = response_scheduling
    return tool
