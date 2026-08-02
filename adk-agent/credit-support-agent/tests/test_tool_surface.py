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

from agent.tooling import (
    ADK_BANKING_MCP_TOOL_ALLOWLIST,
    ADK_RUNTIME_TOOL_NAMES,
    RETIRED_MCP_TOOLS,
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
