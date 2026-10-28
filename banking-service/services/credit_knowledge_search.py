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

"""The grounded knowledge-search port behind the ``search_knowledge`` MCP tool.

Contract (``KnowledgeSearch.search``):
- Returns up to ``page_size`` (clamped to 1..``MAX_PAGE_SIZE``) snippets, each
  proven to be a stored section of the corpus snapshot shipped in this image
  (``services.credit_knowledge_corpus``). An empty result means the live store
  had no match.
- Raises ``KnowledgeUnavailable`` (code ``DEPENDENCY_UNAVAILABLE``) when it
  cannot answer from a grounded index, checked in this order: not configured;
  transport, timeout, auth or status failure; malformed response; any result
  that does not resolve to the shipped snapshot (stale or foreign index).
  It never returns a partial page and never fills a snippet from the local
  corpus; production never falls back to ``InMemoryKnowledgeSearch``.
- Reads no customer data; callers authorize before calling.
"""
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from services.credit_knowledge_corpus import (
    CORPUS_DIR,
    GROUNDED_FIELDS,
    CorpusSnapshot,
    format_citation,
    load_corpus,
)

logger = logging.getLogger(__name__)

DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
DATA_STORE_ENV_VAR = "CREDIT_KNOWLEDGE_DATA_STORE_ID"
LOCATION_ENV_VAR = "CREDIT_KNOWLEDGE_LOCATION"
PROJECT_ENV_VARS = ("CREDIT_KNOWLEDGE_PROJECT_ID", "GOOGLE_CLOUD_PROJECT")
DEFAULT_LOCATION = "global"
SEARCH_TIMEOUT_S = 10.0
CACHE_TTL_S = 1800.0
CACHE_MAX_ENTRIES = 256
MAX_PAGE_SIZE = 5
MAX_SPAN_CHARS = 200


class KnowledgeUnavailable(Exception):
    """Knowledge search cannot give a grounded answer; never an empty success."""

    code = DEPENDENCY_UNAVAILABLE


@dataclass(frozen=True)
class KnowledgeSnippet:
    cite_key: str
    snapshot_id: str
    doc_id: str
    section_id: str
    citation: str
    text_span: str

    def as_tool_result(self) -> dict[str, str]:
        return {
            "cite_key": self.cite_key,
            "doc_id": self.doc_id,
            "section_id": self.section_id,
            "citation": self.citation,
            "text_span": self.text_span,
        }


class SearchHits(tuple):
    """Grounded snippets from one search call, plus whether it was served from cache."""

    snapshot_id: str
    cache_hit: bool

    def __new__(
        cls, snippets: Iterable[KnowledgeSnippet], *, snapshot_id: str, cache_hit: bool = False
    ) -> "SearchHits":
        instance = super().__new__(cls, tuple(snippets))
        instance.snapshot_id = snapshot_id
        instance.cache_hit = cache_hit
        return instance


class KnowledgeSearch(Protocol):
    def search(self, query: str, *, page_size: int) -> SearchHits:
        """Grounded snippets; raises ``KnowledgeUnavailable`` (see module contract)."""
        ...


class UnavailableKnowledge:
    """No data store configured: every search is unavailable, never an empty answer."""

    def search(self, query: str, *, page_size: int) -> SearchHits:
        raise KnowledgeUnavailable("credit knowledge search is not configured")


def _clamp(page_size: int) -> int:
    return max(1, min(int(page_size), MAX_PAGE_SIZE))


def _snippet(record_id: str, fields: Mapping[str, str]) -> KnowledgeSnippet:
    return KnowledgeSnippet(
        cite_key=record_id,
        snapshot_id=fields["snapshot_id"],
        doc_id=fields["doc_id"],
        section_id=fields["section_id"],
        citation=format_citation(fields["short_title"], fields["section_id"], fields["snapshot_id"]),
        text_span=fields["text_span"],
    )


def grounded_snippet(
    record_id: Any, struct_data: Any, records_by_id: Mapping[str, Mapping[str, Any]]
) -> KnowledgeSnippet:
    """One search result as a snippet, built only from the service response.

    The shipped corpus is used only to prove the result is a stored section:
    the same record id and exactly equal grounded fields. Anything else is a
    stale or foreign index and makes the whole search unavailable.
    """
    if not isinstance(struct_data, Mapping):
        raise KnowledgeUnavailable("knowledge search returned a malformed result")
    missing = [f for f in GROUNDED_FIELDS if not isinstance(struct_data.get(f), str) or not struct_data[f].strip()]
    if missing:
        raise KnowledgeUnavailable(
            f"knowledge search result lacks grounded fields {missing}; check the data store schema"
        )
    record_id = str(record_id or "")
    stored = records_by_id.get(record_id)
    hit = {f: struct_data[f] for f in GROUNDED_FIELDS}
    if stored is None or any(hit[f] != stored["structData"][f] for f in GROUNDED_FIELDS):
        raise KnowledgeUnavailable(
            "knowledge search result does not resolve to the shipped snapshot (stale or foreign index)"
        )
    return _snippet(record_id, hit)


def _default_search_client():
    from google.cloud import discoveryengine_v1 as discoveryengine

    return discoveryengine.SearchServiceClient()


def _transport_errors() -> tuple[type[BaseException], ...]:
    from google.api_core import exceptions as api_exceptions
    from google.auth import exceptions as auth_exceptions

    return (
        api_exceptions.GoogleAPIError,
        auth_exceptions.GoogleAuthError,
        TimeoutError,
        ConnectionError,
    )


class DiscoveryEngineKnowledge:
    """Vertex AI Search over the curated data store's ``default_search`` serving config."""

    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        data_store_id: str,
        corpus: CorpusSnapshot,
        client_factory: Callable[[], Any] = _default_search_client,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.serving_config = (
            f"projects/{project_id}/locations/{location}/collections/default_collection"
            f"/dataStores/{data_store_id}/servingConfigs/default_search"
        )
        self._snapshot_id = corpus.snapshot_id
        self._records_by_id = corpus.records_by_id()
        self._client_factory = client_factory
        self._client = None
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: OrderedDict[tuple[str, int, str], tuple[float, tuple[KnowledgeSnippet, ...]]] = OrderedDict()

    def _cached(self, key: tuple[str, int, str]) -> tuple[KnowledgeSnippet, ...] | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if self._clock() - entry[0] >= CACHE_TTL_S:
                del self._cache[key]
                return None
            return entry[1]

    def _store(self, key: tuple[str, int, str], snippets: tuple[KnowledgeSnippet, ...]) -> None:
        with self._lock:
            self._cache[key] = (self._clock(), snippets)
            self._cache.move_to_end(key)
            while len(self._cache) > CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)

    def _results(self, query: str, size: int) -> list[Any]:
        from google.cloud import discoveryengine_v1 as discoveryengine

        try:
            if self._client is None:
                self._client = self._client_factory()
            request = discoveryengine.SearchRequest(
                serving_config=self.serving_config, query=query, page_size=size
            )
            pager = self._client.search(request=request, timeout=SEARCH_TIMEOUT_S)
            # First page only: iterating the pager would fetch further pages.
            return list(pager.results)[:size]
        except _transport_errors() as exc:
            raise KnowledgeUnavailable(f"knowledge search failed ({type(exc).__name__})") from exc

    def search(self, query: str, *, page_size: int) -> SearchHits:
        size = _clamp(page_size)
        key = (query.strip(), size, self._snapshot_id)
        cached = self._cached(key)
        if cached is not None:
            return SearchHits(cached, snapshot_id=self._snapshot_id, cache_hit=True)
        snippets = []
        seen_ids: set[str] = set()
        for result in self._results(key[0], size):
            document = getattr(result, "document", None)
            if document is None:
                raise KnowledgeUnavailable("knowledge search returned a malformed result")
            doc_id = str(getattr(document, "id", "") or "")
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            struct_data = document.struct_data
            snippets.append(
                grounded_snippet(
                    doc_id,
                    dict(struct_data) if isinstance(struct_data, Mapping) else struct_data,
                    self._records_by_id,
                )
            )
        hits = tuple(snippets)
        self._store(key, hits)
        return SearchHits(hits, snapshot_id=self._snapshot_id, cache_hit=False)


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


class InMemoryKnowledgeSearch:
    """Lexical search over the shipped snapshot; for tests and offline evaluation only."""

    def __init__(self, corpus: CorpusSnapshot) -> None:
        self._snapshot_id = corpus.snapshot_id
        self._records = corpus.records

    def search(self, query: str, *, page_size: int) -> SearchHits:
        size = _clamp(page_size)
        terms = _tokens(query)
        scored = []
        for record in self._records:
            struct = record["structData"]
            text = " ".join(str(struct.get(f, "")) for f in ("short_title", "heading", "text_span"))
            score = len(terms & _tokens(text))
            if score:
                scored.append((-score, record["id"], record))
        scored.sort(key=lambda item: (item[0], item[1]))
        snippets = [
            _snippet(record["id"], {f: record["structData"][f] for f in GROUNDED_FIELDS})
            for _, _, record in scored[:size]
        ]
        return SearchHits(snippets, snapshot_id=self._snapshot_id, cache_hit=False)


def credit_knowledge_search_from_env(
    environ: Mapping[str, str] | None = None,
    *,
    corpus_dir: Path = CORPUS_DIR,
    client_factory: Callable[[], Any] = _default_search_client,
) -> KnowledgeSearch:
    """The configured port, or ``UnavailableKnowledge`` when the data store or
    project is unset or the shipped snapshot cannot be loaded."""
    environ = os.environ if environ is None else environ
    data_store_id = environ.get(DATA_STORE_ENV_VAR, "").strip()
    project_id = next((environ.get(k, "").strip() for k in PROJECT_ENV_VARS if environ.get(k, "").strip()), "")
    if not data_store_id or not project_id:
        logger.warning("Credit knowledge search is not configured; searches are unavailable.")
        return UnavailableKnowledge()
    location = environ.get(LOCATION_ENV_VAR, "").strip() or DEFAULT_LOCATION
    try:
        corpus = load_corpus(corpus_dir)
    except (OSError, ValueError, KeyError) as exc:
        logger.error("Credit knowledge corpus could not be loaded error_type=%s", type(exc).__name__)
        return UnavailableKnowledge()
    return DiscoveryEngineKnowledge(
        project_id=project_id,
        location=location,
        data_store_id=data_store_id,
        corpus=corpus,
        client_factory=client_factory,
    )
