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

"""KnowledgeSearch port: fail-closed adapters, grounding check, cache."""
import copy
from types import SimpleNamespace

import pytest
from google.api_core import exceptions as api_exceptions
from google.auth import exceptions as auth_exceptions

from services.credit_knowledge_corpus import load_corpus
from services.credit_knowledge_search import (
    CACHE_MAX_ENTRIES,
    CACHE_TTL_S,
    SEARCH_TIMEOUT_S,
    DiscoveryEngineKnowledge,
    InMemoryKnowledgeSearch,
    KnowledgeUnavailable,
    UnavailableKnowledge,
    credit_knowledge_search_from_env,
)

CORPUS = load_corpus()
FEES_ID = "CARD-CASHBACK_EVERYDAY-fees"


def _stored(record_id):
    return copy.deepcopy(CORPUS.records_by_id()[record_id])


def _result(record_id, struct_data):
    return SimpleNamespace(document=SimpleNamespace(id=record_id, struct_data=struct_data))


class FakeSearchClient:
    def __init__(self, results=(), error=None):
        self.results = list(results)
        self.error = error
        self.calls = []

    def search(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return SimpleNamespace(results=self.results)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _adapter(client, clock=None):
    return DiscoveryEngineKnowledge(
        project_id="proj", location="global", data_store_id="credit-knowledge",
        corpus=CORPUS, client_factory=lambda: client, clock=clock or Clock(),
    )


def _ok_client(*record_ids):
    return FakeSearchClient([_result(rid, _stored(rid)["structData"]) for rid in record_ids])


# --- Shared conformance: any implementation returns grounded snippets of the shipped snapshot.

@pytest.fixture(params=["in_memory", "discovery_engine"])
def search_port(request):
    if request.param == "in_memory":
        return InMemoryKnowledgeSearch(CORPUS)
    return _adapter(_ok_client(FEES_ID, "POLICY-FEES-overview"))


def test_conformance_snippets_are_grounded_in_the_shipped_snapshot(search_port):
    hits = search_port.search("late fee Everyday Cash", page_size=3)
    assert hits.snapshot_id == CORPUS.snapshot_id
    assert 0 < len(hits) <= 3
    assert hits[0].cite_key == FEES_ID
    for snippet in hits:
        stored = CORPUS.records_by_id()[snippet.cite_key]["structData"]
        assert snippet.doc_id == stored["doc_id"]
        assert snippet.section_id == stored["section_id"]
        assert snippet.text_span == stored["text_span"]
        assert snippet.citation == stored["citation"]
        assert set(snippet.as_tool_result()) == {"cite_key", "doc_id", "section_id", "citation", "text_span"}


def test_conformance_page_size_is_clamped_to_five(search_port):
    assert len(search_port.search("fee APR card", page_size=50)) <= 5


# --- Fail closed.

def test_unconfigured_port_is_unavailable_never_empty():
    with pytest.raises(KnowledgeUnavailable) as excinfo:
        UnavailableKnowledge().search("late fee", page_size=3)
    assert excinfo.value.code == "DEPENDENCY_UNAVAILABLE"


@pytest.mark.parametrize("environ", [
    {},
    {"CREDIT_KNOWLEDGE_DATA_STORE_ID": "credit-knowledge"},
    {"CREDIT_KNOWLEDGE_PROJECT_ID": "proj"},
    {"CREDIT_KNOWLEDGE_DATA_STORE_ID": " ", "CREDIT_KNOWLEDGE_PROJECT_ID": "proj"},
])
def test_factory_without_store_or_project_is_unavailable(environ):
    assert isinstance(credit_knowledge_search_from_env(environ), UnavailableKnowledge)


def test_factory_with_unloadable_corpus_is_unavailable(tmp_path):
    environ = {"CREDIT_KNOWLEDGE_DATA_STORE_ID": "credit-knowledge", "CREDIT_KNOWLEDGE_PROJECT_ID": "proj"}
    assert isinstance(credit_knowledge_search_from_env(environ, corpus_dir=tmp_path), UnavailableKnowledge)


def test_factory_when_configured_targets_the_curated_store_serving_config():
    environ = {"CREDIT_KNOWLEDGE_DATA_STORE_ID": "credit-knowledge", "GOOGLE_CLOUD_PROJECT": "proj"}
    port = credit_knowledge_search_from_env(environ, client_factory=lambda: None)
    assert isinstance(port, DiscoveryEngineKnowledge)
    assert port.serving_config == (
        "projects/proj/locations/global/collections/default_collection"
        "/dataStores/credit-knowledge/servingConfigs/default_search"
    )


@pytest.mark.parametrize("error", [
    api_exceptions.ServiceUnavailable("down"),
    api_exceptions.DeadlineExceeded("slow"),
    api_exceptions.PermissionDenied("iam"),
    api_exceptions.NotFound("no store"),
    auth_exceptions.DefaultCredentialsError("no adc"),
    TimeoutError("socket"),
])
def test_transport_failures_are_unavailable(error):
    with pytest.raises(KnowledgeUnavailable):
        _adapter(FakeSearchClient(error=error)).search("late fee", page_size=3)


def test_client_construction_failure_is_unavailable():
    def boom():
        raise auth_exceptions.DefaultCredentialsError("no adc")

    port = DiscoveryEngineKnowledge(
        project_id="p", location="global", data_store_id="d", corpus=CORPUS, client_factory=boom
    )
    with pytest.raises(KnowledgeUnavailable):
        port.search("late fee", page_size=3)


def test_request_uses_timeout_clamped_size_and_reads_only_the_first_page():
    client = _ok_client(*[r["id"] for r in CORPUS.records[:8]])
    hits = _adapter(client).search("  fees  ", page_size=9)
    request, timeout = client.calls[0]
    assert timeout == SEARCH_TIMEOUT_S
    assert request.page_size == 5
    assert request.query == "fees"
    assert len(hits) == 5


# --- Grounding check.

def _search_with(struct_data, record_id=FEES_ID):
    return _adapter(FakeSearchClient([_result(record_id, struct_data)])).search("late fee", page_size=3)


@pytest.mark.parametrize("field", ["doc_id", "section_id", "short_title", "snapshot_id", "text_span"])
def test_result_missing_a_grounded_field_is_unavailable(field):
    struct = _stored(FEES_ID)["structData"]
    del struct[field]
    with pytest.raises(KnowledgeUnavailable, match="lacks grounded fields"):
        _search_with(struct)


def test_result_from_another_snapshot_is_unavailable():
    struct = _stored(FEES_ID)["structData"]
    struct["snapshot_id"] = "1-000000000000"
    with pytest.raises(KnowledgeUnavailable, match="stale or foreign"):
        _search_with(struct)


def test_result_with_unknown_id_is_unavailable():
    with pytest.raises(KnowledgeUnavailable, match="stale or foreign"):
        _search_with(_stored(FEES_ID)["structData"], record_id="CARD-UNKNOWN-fees")


def test_result_whose_fields_belong_to_another_record_is_unavailable():
    with pytest.raises(KnowledgeUnavailable, match="stale or foreign"):
        _search_with(_stored("POLICY-FEES-overview")["structData"], record_id=FEES_ID)


def test_result_with_drifted_text_is_unavailable():
    struct = _stored(FEES_ID)["structData"]
    struct["text_span"] = struct["text_span"].replace("40.00", "4.00")
    with pytest.raises(KnowledgeUnavailable, match="stale or foreign"):
        _search_with(struct)


@pytest.mark.parametrize("result", [
    SimpleNamespace(document=None),
    SimpleNamespace(document=SimpleNamespace(id=FEES_ID, struct_data="not-a-map")),
    SimpleNamespace(),
])
def test_malformed_results_are_unavailable(result):
    with pytest.raises(KnowledgeUnavailable):
        _adapter(FakeSearchClient([result])).search("late fee", page_size=3)


def test_one_bad_result_fails_the_whole_page():
    good = _result(FEES_ID, _stored(FEES_ID)["structData"])
    bad = _result("CARD-UNKNOWN-x", _stored(FEES_ID)["structData"])
    with pytest.raises(KnowledgeUnavailable):
        _adapter(FakeSearchClient([good, bad])).search("late fee", page_size=3)


def test_empty_live_result_is_an_empty_grounded_answer():
    hits = _adapter(FakeSearchClient([])).search("unrelated", page_size=3)
    assert tuple(hits) == () and hits.snapshot_id == CORPUS.snapshot_id


# --- Cache.

def test_repeat_query_is_served_from_cache_until_ttl():
    client, clock = _ok_client(FEES_ID), Clock()
    port = _adapter(client, clock)
    assert port.search("late fee", page_size=3).cache_hit is False
    clock.now += CACHE_TTL_S - 1
    hit = port.search(" late fee ", page_size=3)
    assert hit.cache_hit is True and hit[0].cite_key == FEES_ID
    assert len(client.calls) == 1
    clock.now += 1
    assert port.search("late fee", page_size=3).cache_hit is False
    assert len(client.calls) == 2


def test_cache_key_includes_page_size():
    client = _ok_client(FEES_ID)
    port = _adapter(client)
    port.search("late fee", page_size=3)
    assert port.search("late fee", page_size=2).cache_hit is False
    assert len(client.calls) == 2


def test_failures_are_not_cached():
    client = FakeSearchClient(error=api_exceptions.ServiceUnavailable("down"))
    port = _adapter(client)
    with pytest.raises(KnowledgeUnavailable):
        port.search("late fee", page_size=3)
    client.error = None
    client.results = [_result(FEES_ID, _stored(FEES_ID)["structData"])]
    assert port.search("late fee", page_size=3).cache_hit is False


def test_cache_is_bounded_and_evicts_oldest():
    client = _ok_client(FEES_ID)
    port = _adapter(client)
    for index in range(CACHE_MAX_ENTRIES + 1):
        port.search(f"query {index}", page_size=3)
    calls = len(client.calls)
    assert port.search(f"query {CACHE_MAX_ENTRIES}", page_size=3).cache_hit is True
    assert port.search("query 0", page_size=3).cache_hit is False
    assert len(client.calls) == calls + 1


def test_real_discovery_engine_response_shape_is_grounded():
    from google.cloud import discoveryengine_v1 as discoveryengine

    stored = _stored(FEES_ID)
    response = discoveryengine.SearchResponse(results=[
        discoveryengine.SearchResponse.SearchResult(
            id=FEES_ID,
            document=discoveryengine.Document(id=FEES_ID, struct_data=stored["structData"]),
        )
    ])

    class ProtoClient(FakeSearchClient):
        def search(self, request, timeout):
            self.calls.append((request, timeout))
            return response

    hits = _adapter(ProtoClient()).search("late fee", page_size=3)
    assert [s.cite_key for s in hits] == [FEES_ID]
    assert hits[0].text_span == stored["structData"]["text_span"]
