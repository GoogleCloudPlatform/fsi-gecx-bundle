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

"""search_knowledge MCP tool: contract, validation, fail-closed envelope, caller auth."""
import logging
from unittest.mock import MagicMock

import pytest

import routers.mcp.knowledge as knowledge_tool
from routers.mcp import mcp
from routers.mcp.knowledge import search_knowledge
from services.credit_knowledge_corpus import load_corpus
from services.credit_knowledge_search import InMemoryKnowledgeSearch, UnavailableKnowledge

CORPUS = load_corpus()


def _ctx(headers=None):
    ctx = MagicMock()
    ctx.request_context.request.headers = dict(headers or {})
    return ctx


SUPPORT_CTX_HEADERS = {"x-target-customer-id": "customer-123"}


@pytest.fixture(autouse=True)
def local_runtime(monkeypatch):
    monkeypatch.delenv("K_SERVICE", raising=False)


@pytest.fixture
def in_memory(monkeypatch):
    port = InMemoryKnowledgeSearch(CORPUS)
    monkeypatch.setattr(knowledge_tool, "get_knowledge_search", lambda: port)
    return port


@pytest.mark.asyncio
async def test_happy_path_returns_cited_grounded_snippets(in_memory, caplog):
    caplog.set_level(logging.INFO, logger="routers.mcp.knowledge")
    query = "What is the late fee on Everyday Cash?"
    result = await search_knowledge(query=query, ctx=_ctx(SUPPORT_CTX_HEADERS))

    assert result["success"] is True
    assert set(result) == {"success", "snapshot_id", "snippets"}
    assert result["snapshot_id"] == CORPUS.snapshot_id
    assert 0 < len(result["snippets"]) <= 3
    first = result["snippets"][0]
    assert set(first) == {"cite_key", "doc_id", "section_id", "citation", "text_span"}
    assert first["cite_key"] == "CARD-CASHBACK_EVERYDAY-fees"
    assert "Late fee: up to USD 40.00" in first["text_span"]
    assert first["citation"].endswith(f"(snapshot {CORPUS.snapshot_id})")

    logs = " ".join(record.getMessage() for record in caplog.records)
    assert "CARD-CASHBACK_EVERYDAY-fees" in logs and "cache_hit=false" in logs
    assert "Everyday Cash?" not in logs and "late fee" not in logs.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "   ", "x" * 501, " " + "y" * 501 + " "])
async def test_invalid_queries_are_refused_without_searching(query, monkeypatch):
    port = MagicMock()
    monkeypatch.setattr(knowledge_tool, "get_knowledge_search", lambda: port)
    result = await search_knowledge(query=query, ctx=_ctx(SUPPORT_CTX_HEADERS))
    assert result == {"success": False, "error": "INVALID_QUERY", "message": "Query must be 1-500 characters."}
    port.search.assert_not_called()


@pytest.mark.asyncio
async def test_query_of_500_chars_after_strip_is_accepted(in_memory):
    result = await search_knowledge(query="  " + "fee " * 125 + "  ", ctx=_ctx(SUPPORT_CTX_HEADERS))
    assert result["success"] is True


@pytest.mark.asyncio
async def test_unconfigured_search_is_dependency_unavailable(monkeypatch):
    monkeypatch.setattr(knowledge_tool, "get_knowledge_search", lambda: UnavailableKnowledge())
    result = await search_knowledge(query="late fee", ctx=_ctx(SUPPORT_CTX_HEADERS))
    assert result == {
        "success": False,
        "error": "DEPENDENCY_UNAVAILABLE",
        "message": "Knowledge search is unavailable right now.",
    }


@pytest.mark.asyncio
async def test_unexpected_port_failure_is_dependency_unavailable(monkeypatch):
    port = MagicMock()
    port.search.side_effect = RuntimeError("bug")
    monkeypatch.setattr(knowledge_tool, "get_knowledge_search", lambda: port)
    result = await search_knowledge(query="late fee", ctx=_ctx(SUPPORT_CTX_HEADERS))
    assert result["error"] == "DEPENDENCY_UNAVAILABLE"


# --- Caller authentication: identical gate to sibling banking MCP tools.

@pytest.mark.asyncio
async def test_cloud_run_call_without_caller_token_is_refused(in_memory, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "banking-service")
    with pytest.raises(PermissionError, match="Missing or invalid Authorization header"):
        await search_knowledge(query="late fee", ctx=_ctx(SUPPORT_CTX_HEADERS))


@pytest.mark.asyncio
async def test_cloud_run_call_with_unverifiable_caller_token_is_refused(in_memory, monkeypatch):
    monkeypatch.setenv("K_SERVICE", "banking-service")

    def reject(token):
        raise ValueError("bad signature")

    monkeypatch.setattr("utils.auth.validate_google_id_token", reject)
    headers = {**SUPPORT_CTX_HEADERS, "authorization": "Bearer forged"}
    with pytest.raises(PermissionError, match="caller token verification failed"):
        await search_knowledge(query="late fee", ctx=_ctx(headers))


@pytest.mark.asyncio
async def test_missing_user_assertion_is_refused(in_memory):
    with pytest.raises(ValueError, match="Missing Firebase user assertion token"):
        await search_knowledge(query="late fee", ctx=_ctx())


@pytest.mark.asyncio
async def test_invalid_user_assertion_is_refused(in_memory, monkeypatch):
    def reject(token):
        raise ValueError("Invalid signature")

    monkeypatch.setattr("routers.mcp.utils.validate_firebase_token", reject)
    with pytest.raises(PermissionError, match="Invalid assertion token"):
        await search_knowledge(query="late fee", assertion_token="bad-token", ctx=_ctx())


@pytest.mark.asyncio
async def test_published_schema_is_query_only():
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    schema = tools["search_knowledge"].parameters
    assert set(schema["properties"]) == {"query"}
    assert schema["required"] == ["query"]
    assert schema["properties"]["query"]["type"] == "string"
