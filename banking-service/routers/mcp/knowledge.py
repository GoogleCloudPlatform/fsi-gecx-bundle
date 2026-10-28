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

"""Read-only, grounded support-knowledge search for banking agents."""

import asyncio
import logging
from functools import lru_cache

from fastmcp import Context

from . import mcp
from .utils import requires_user_assertion
from services.credit_knowledge_search import (
    KnowledgeSearch,
    KnowledgeUnavailable,
    credit_knowledge_search_from_env,
)
from utils.log_safety import stable_log_reference

logger = logging.getLogger(__name__)

MAX_QUERY_CHARS = 500
PAGE_SIZE = 3


@lru_cache(maxsize=1)
def get_knowledge_search() -> KnowledgeSearch:
    return credit_knowledge_search_from_env()


def _unavailable() -> dict:
    return {
        "success": False,
        "error": KnowledgeUnavailable.code,
        "message": "Knowledge search is unavailable right now.",
    }


@mcp.tool()
@requires_user_assertion
async def search_knowledge(query: str, ctx: Context = None) -> dict:
    """Search Nova Horizon's curated credit card knowledge: card terms (APRs, fees,
    rewards, credit limit ranges, features) and general how-to and policy guidance
    (applying, payments, limit increases, secured card graduation, lost or stolen
    cards, disputes, fees, contacting support).

    Returns up to three cited snippets. Answer only from the snippet text and cite
    each fact with its cite_key. This tool reads no customer or account data and
    does not establish eligibility or perform any action.
    """
    normalized = query.strip() if isinstance(query, str) else ""
    if not normalized or len(normalized) > MAX_QUERY_CHARS:
        return {
            "success": False,
            "error": "INVALID_QUERY",
            "message": f"Query must be 1-{MAX_QUERY_CHARS} characters.",
        }
    query_ref = stable_log_reference(normalized, "knowledge_query")
    try:
        hits = await asyncio.to_thread(
            get_knowledge_search().search, normalized, page_size=PAGE_SIZE
        )
    except KnowledgeUnavailable as exc:
        logger.warning(
            "search_knowledge unavailable query_ref=%s error_type=%s",
            query_ref,
            type(exc.__cause__ or exc).__name__,
        )
        return _unavailable()
    except Exception as exc:
        logger.error(
            "search_knowledge failed query_ref=%s error_type=%s", query_ref, type(exc).__name__
        )
        return _unavailable()

    cite_keys = [snippet.cite_key for snippet in hits]
    logger.info(
        "search_knowledge served query_ref=%s query_chars=%d cache_hit=%s snapshot_id=%s cite_keys=%s",
        query_ref,
        len(normalized),
        str(hits.cache_hit).lower(),
        hits.snapshot_id,
        ",".join(cite_keys) or "none",
    )
    return {
        "success": True,
        "snapshot_id": hits.snapshot_id,
        "snippets": [snippet.as_tool_result() for snippet in hits],
    }
