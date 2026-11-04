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

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

import main


EXPECTED_MCP_TOOLS = {
    "inspect_synthetic_schedule",
    "create_scenario_plan",
    "enqueue_synthetic_story",
    "cancel_future_synthetic_events",
    "adjust_ambient_load_profile",
}


@pytest.mark.asyncio
async def test_data_generator_mcp_http_surface_lists_tools() -> None:
    mcp_app = main.data_generator_mcp_app
    assert mcp_app is not None, "FastMCP control surface failed to initialize"

    async with (
        mcp_app.lifespan(mcp_app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp_app)) as http_client,
        streamable_http_client("http://test/", http_client=http_client) as (
            read,
            write,
            _,
        ),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools_result = await session.list_tools()

    assert EXPECTED_MCP_TOOLS <= {tool.name for tool in tools_result.tools}
