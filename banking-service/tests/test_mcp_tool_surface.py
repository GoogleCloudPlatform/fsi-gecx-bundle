import pytest

from routers.mcp import mcp


RETIRED_TOOLS = {
    "report_lost_stolen_card",
    "issue_replacement_card_tool",
    "push_card_to_google_wallet",
    "resolve_fraud_alert",
    "triage_fraud_case",
}


@pytest.mark.asyncio
async def test_retired_direct_actions_are_not_published_over_mcp() -> None:
    published = {tool.name for tool in await mcp.list_tools()}

    assert published.isdisjoint(RETIRED_TOOLS)
    assert {
        "propose_card_reissue",
        "commit_card_reissue",
        "propose_wallet_provisioning",
        "commit_wallet_provisioning",
        "propose_fraud_triage",
        "commit_fraud_triage",
    } <= published
