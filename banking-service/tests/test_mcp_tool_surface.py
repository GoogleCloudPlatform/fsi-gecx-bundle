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

import pytest

from routers.mcp import mcp


RETIRED_TOOLS = {
    "report_lost_stolen_card",
    "issue_replacement_card_tool",
    "push_card_to_google_wallet",
    "resolve_fraud_alert",
    "triage_fraud_case",
}

PROPOSAL_TOOL_SCHEMAS = {
    "propose_fraud_triage": {
        "properties": {
            "fraud_alert_id",
            "selection_status",
            "disputed_authorization_ids",
            "disputed_transaction_ids",
            "recognized_authorization_ids",
            "recognized_transaction_ids",
            "issue_replacement",
            "escalate",
        },
        "required": {"fraud_alert_id", "selection_status"},
    },
    "commit_fraud_triage": {
        "properties": {"proposal_id"},
        "required": {"proposal_id"},
    },
    "propose_card_reissue": {
        "properties": {"reason"},
        "required": {"reason"},
    },
    "commit_card_reissue": {
        "properties": {"proposal_id"},
        "required": {"proposal_id"},
    },
    "propose_wallet_provisioning": {
        "properties": set(),
        "required": set(),
    },
    "commit_wallet_provisioning": {
        "properties": {"proposal_id"},
        "required": {"proposal_id"},
    },
    "decide_action_proposal": {
        "properties": {"proposal_id", "decision"},
        "required": {"proposal_id", "decision"},
    },
}

PROTECTED_TRANSPORT_FIELDS = {
    "customer_id",
    "support_session_id",
    "runtime_name",
    "runtime_session_id",
    "customer_turn_id",
    "reset_generation",
    "presentation_turn_id",
    "confirmation_turn_id",
    "confirmation_method",
    "confirmation_source",
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


@pytest.mark.asyncio
async def test_model_visible_proposal_tool_schemas_are_frozen() -> None:
    published = {tool.name: tool for tool in await mcp.list_tools()}

    for tool_name, expected in PROPOSAL_TOOL_SCHEMAS.items():
        schema = published[tool_name].parameters
        properties = set(schema.get("properties", {}))
        required = set(schema.get("required", []))

        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert properties == expected["properties"]
        assert required == expected["required"]
        assert properties.isdisjoint(PROTECTED_TRANSPORT_FIELDS)

    decision_schema = published["decide_action_proposal"].parameters
    assert set(decision_schema["properties"]["decision"]["enum"]) == {
        "DECLINE",
        "REVISE",
        "CANCEL",
    }


@pytest.mark.asyncio
async def test_closeout_wrapper_exposes_only_the_terminal_reason() -> None:
    published = {tool.name: tool for tool in await mcp.list_tools()}

    schema = published["complete_consultation"].parameters
    assert set(schema["properties"]) == {"reason"}
    assert schema["required"] == ["reason"]
    assert schema["properties"]["reason"]["const"] == "customer_query_ended"
