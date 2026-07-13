"""ADK tool adapters used by the Live voice agent."""

from __future__ import annotations

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool import McpToolset
from google.genai import types


class LiveMcpToolset(McpToolset):
    """Apply one explicit Live response policy to dynamically loaded MCP tools."""

    async def get_tools(
        self,
        readonly_context: ReadonlyContext | None = None,
    ) -> list[BaseTool]:
        tools = await super().get_tools(readonly_context)
        for tool in tools:
            configure_live_tool(tool)
        return tools


def configure_live_tool(tool: BaseTool) -> BaseTool:
    """Apply the voice agent's ADK 2.4 function-response policy."""
    # MCP results should be observed after the current model activity is idle,
    # rather than interrupting speech or racing a second response.
    tool.response_scheduling = types.FunctionResponseScheduling.WHEN_IDLE
    return tool

