from types import SimpleNamespace

from agent.tooling import (
    ADK_BANKING_MCP_TOOL_ALLOWLIST,
    ADK_RUNTIME_TOOL_NAMES,
    RETIRED_MCP_TOOLS,
    project_adk_banking_tools,
)


def test_adk_banking_tool_projection_is_an_explicit_allowlist() -> None:
    advertised = [
        SimpleNamespace(name="get_open_fraud_alert"),
        SimpleNamespace(name="offer_session_closeout"),
        SimpleNamespace(name="push_card_to_google_wallet"),
        SimpleNamespace(name="unexpected_future_tool"),
    ]

    projected = project_adk_banking_tools(advertised)

    assert [tool.name for tool in projected] == ["get_open_fraud_alert"]


def test_adk_banking_and_runtime_tool_names_are_unique() -> None:
    assert ADK_BANKING_MCP_TOOL_ALLOWLIST.isdisjoint(ADK_RUNTIME_TOOL_NAMES)
    assert "offer_session_closeout" in ADK_RUNTIME_TOOL_NAMES
    assert "offer_session_closeout" not in ADK_BANKING_MCP_TOOL_ALLOWLIST
    assert ADK_BANKING_MCP_TOOL_ALLOWLIST.isdisjoint(RETIRED_MCP_TOOLS)
