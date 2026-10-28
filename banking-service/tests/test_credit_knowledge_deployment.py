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

"""Credit knowledge store deployment: least-privilege IAM and the import job."""
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.api_core import exceptions as api_exceptions
from google.cloud import discoveryengine_v1 as discoveryengine

from services.credit_knowledge_corpus import GROUNDED_FIELDS, CorpusSnapshot, load_corpus

REPO = Path(__file__).resolve().parents[2]
TERRAFORM = REPO / "deployment" / "terraform"
KNOWLEDGE_TF = (TERRAFORM / "credit_knowledge.tf").read_text()
STORE = "projects/p/locations/global/collections/default_collection/dataStores/credit-knowledge"


def _block(kind: str, name: str, text: str = KNOWLEDGE_TF) -> str:
    match = re.search(rf'resource "{kind}" "{name}" \{{(.*?)\n\}}', text, re.S)
    assert match, f"{kind}.{name} missing"
    return match.group(1)


def _permissions(role_block: str) -> set[str]:
    return set(re.findall(r'"(discoveryengine\.[a-zA-Z.]+)"', role_block))


def test_runtime_sa_gets_only_the_search_permission():
    role = _block("google_project_iam_custom_role", "credit_knowledge_searcher")
    assert _permissions(role) == {"discoveryengine.servingConfigs.search"}
    binding = _block("google_project_iam_member", "banking_service_sa_credit_knowledge_searcher")
    assert "google_project_iam_custom_role.credit_knowledge_searcher.id" in binding
    assert "google_service_account.banking_service_account.email" in binding


def test_only_the_import_identity_can_write_and_it_cannot_administer():
    role = _block("google_project_iam_custom_role", "credit_knowledge_importer")
    permissions = _permissions(role)
    assert permissions == {
        "discoveryengine.documents.delete",
        "discoveryengine.documents.import",
        "discoveryengine.documents.list",
        "discoveryengine.operations.get",
        "discoveryengine.schemas.get",
        "discoveryengine.schemas.update",
    }
    # Document-level writes only: no data store, engine, serving config or schema lifecycle.
    assert not any(
        p.startswith(("discoveryengine.dataStores.", "discoveryengine.engines.", "discoveryengine.servingConfigs."))
        or p.endswith((".create", ".setIamPolicy"))
        or p == "discoveryengine.schemas.delete"
        for p in permissions
    )

    binding = _block("google_project_iam_member", "credit_knowledge_import_sa_importer")
    assert "credit_knowledge_import_service_account.email" in binding
    importer_members = re.findall(
        r"role\s+=\s+google_project_iam_custom_role\.credit_knowledge_importer\.id\s+member\s+=\s+(.*)",
        "".join((TERRAFORM / f).read_text() for f in sorted(p.name for p in TERRAFORM.glob("*.tf"))),
    )
    assert importer_members == [
        '"serviceAccount:${google_service_account.credit_knowledge_import_service_account.email}"'
    ]


def test_no_new_admin_or_editor_discovery_engine_grant_for_the_runtime_sa():
    all_tf = "".join(p.read_text() for p in TERRAFORM.glob("*.tf"))
    grants = re.findall(
        r'role\s+=\s+"(roles/discoveryengine\.[a-zA-Z]+)"\s+member\s+=\s+"serviceAccount:\$\{google_service_account\.banking_service_account\.email\}"',
        all_tf,
    )
    assert grants == ["roles/discoveryengine.viewer"]  # pre-existing, for site search


def test_curated_store_is_separate_from_the_site_search_engine():
    store = _block("google_discovery_engine_data_store", "credit_knowledge")
    assert 'data_store_id               = "credit-knowledge"' in store
    assert '"SOLUTION_TYPE_SEARCH"' in store
    engine = _block(
        "google_discovery_engine_search_engine",
        "nova_horizon_site",
        (TERRAFORM / "discovery_engine.tf").read_text(),
    )
    assert "credit_knowledge" not in engine


def test_import_job_runs_as_the_import_identity():
    job = _block("google_cloud_run_v2_job", "credit_knowledge_import")
    assert "google_service_account.credit_knowledge_import_service_account.email" in job
    assert '"scripts/import_credit_knowledge.py"' in job


# --- Import script, against fake Discovery Engine clients.

def _import_module():
    path = REPO / "banking-service" / "scripts" / "import_credit_knowledge.py"
    spec = importlib.util.spec_from_file_location("import_credit_knowledge", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


importer = _import_module()


class FakeOperation:
    def __init__(self, response=None, metadata=None):
        self.response = response
        self.metadata = metadata

    def result(self, timeout):
        return self.response


class FakeSchemaClient:
    def __init__(self, current=None):
        self.current = current
        self.updates = []

    def get_schema(self, name):
        if self.current is None:
            raise api_exceptions.NotFound("none")
        return self.current

    def update_schema(self, request):
        self.updates.append(request)
        self.current = request.schema
        return FakeOperation()


def test_schema_makes_grounded_fields_retrievable():
    schema = importer.corpus_json_schema()
    for field in GROUNDED_FIELDS:
        assert schema["properties"][field]["retrievable"] is True
    assert schema["properties"]["text_span"]["searchable"] is True


def test_schema_apply_is_idempotent_and_logs_fields(caplog):
    caplog.set_level("INFO")
    client = FakeSchemaClient()
    assert importer.apply_schema(client, STORE) is True
    assert client.updates[0].schema.name == f"{STORE}/schemas/default_schema"
    assert client.updates[0].allow_missing is True
    assert importer.apply_schema(client, STORE) is False
    assert len(client.updates) == 1
    assert "fields=citation,doc_id" in caplog.text


class FakeDocumentClient:
    """In-memory branch: import upserts, list paginates, delete removes."""

    def __init__(self, failure_count=0, error_messages=(), stored_ids=(), page_size=2, failing_deletes=()):
        self.failure_count = failure_count
        self.error_messages = error_messages
        self.page_size = page_size
        self.failing_deletes = set(failing_deletes)
        self.requests = []
        self.list_requests = []
        self.deleted = []
        self.store = {doc_id: f"{STORE}/branches/default_branch/documents/{doc_id}" for doc_id in stored_ids}

    def import_documents(self, request):
        self.requests.append(request)
        for document in request.inline_source.documents:
            self.store[document.id] = f"{request.parent}/documents/{document.id}"
        response = SimpleNamespace(error_samples=[SimpleNamespace(message=m) for m in self.error_messages])
        return FakeOperation(response, SimpleNamespace(failure_count=self.failure_count))

    def list_documents(self, request):
        self.list_requests.append(request)
        ids = sorted(self.store)
        start = int(request.page_token or 0)
        page = ids[start:start + self.page_size]
        next_token = str(start + self.page_size) if start + self.page_size < len(ids) else ""
        documents = [SimpleNamespace(id=doc_id, name=self.store[doc_id]) for doc_id in page]
        return SimpleNamespace(documents=documents, next_page_token=next_token)

    def delete_document(self, request):
        doc_id = request.name.rsplit("/", 1)[-1]
        if doc_id in self.failing_deletes:
            raise api_exceptions.ServiceUnavailable("down")
        self.deleted.append(doc_id)
        self.store.pop(doc_id, None)


INCREMENTAL = discoveryengine.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL
FULL = discoveryengine.ImportDocumentsRequest.ReconciliationMode.FULL


def test_import_upserts_the_whole_snapshot_incrementally_in_one_request():
    corpus = load_corpus()
    client = FakeDocumentClient()
    assert importer.import_snapshot(client, STORE, corpus) == len(corpus.records)
    (request,) = client.requests
    assert request.parent == f"{STORE}/branches/default_branch"
    assert request.reconciliation_mode == INCREMENTAL
    documents = request.inline_source.documents
    assert [d.id for d in documents] == [r["id"] for r in corpus.records]
    assert dict(documents[0].struct_data) == corpus.records[0]["structData"]


def test_inline_import_never_uses_full_reconciliation():
    # Regression guard: Discovery Engine rejects inlineSource with FULL (400 InvalidArgument).
    client = FakeDocumentClient()
    importer.import_snapshot(client, STORE, load_corpus())
    for request in client.requests:
        if request.inline_source.documents:
            assert request.reconciliation_mode != FULL


def test_prune_deletes_only_ids_missing_from_the_snapshot_across_pages(caplog):
    caplog.set_level("INFO")
    corpus = load_corpus()
    snapshot_ids = [r["id"] for r in corpus.records]
    stale = ["CARD-RETIRED-fees", "POLICY-OLD-x", "ZZZ-last-page"]
    client = FakeDocumentClient(stored_ids=snapshot_ids[:5] + stale, page_size=3)
    importer.import_snapshot(client, STORE, corpus)

    kept, deleted = importer.prune_documents(client, STORE, corpus)

    assert sorted(client.deleted) == sorted(stale)
    assert (kept, deleted) == (len(snapshot_ids), len(stale))
    assert sorted(client.store) == sorted(snapshot_ids)
    assert len(client.list_requests) > 2  # walked every page
    assert all(r.parent == f"{STORE}/branches/default_branch" for r in client.list_requests)
    assert f"kept={len(snapshot_ids)} deleted={len(stale)} failed=0" in caplog.text


def test_rerun_with_the_same_snapshot_deletes_nothing():
    corpus = load_corpus()
    client = FakeDocumentClient(stored_ids=["CARD-RETIRED-fees"])
    for _ in range(2):
        importer.import_snapshot(client, STORE, corpus)
        importer.prune_documents(client, STORE, corpus)
    assert client.deleted == ["CARD-RETIRED-fees"]
    assert importer.prune_documents(client, STORE, corpus) == (len(corpus.records), 0)


def test_delete_failure_exits_non_zero_after_attempting_the_rest():
    corpus = load_corpus()
    client = FakeDocumentClient(stored_ids=["A-stale", "B-stale"], failing_deletes=["A-stale"])
    importer.import_snapshot(client, STORE, corpus)
    with pytest.raises(RuntimeError, match="prune failed for 1 document"):
        importer.prune_documents(client, STORE, corpus)
    assert client.deleted == ["B-stale"]


def test_prune_refuses_an_empty_snapshot():
    corpus = load_corpus()
    client = FakeDocumentClient(stored_ids=[r["id"] for r in corpus.records])
    with pytest.raises(ValueError, match="empty snapshot"):
        importer.prune_documents(client, STORE, CorpusSnapshot(corpus.manifest, ()))
    assert client.deleted == []


def test_main_imports_before_pruning(monkeypatch):
    calls = []
    monkeypatch.setenv("CREDIT_KNOWLEDGE_PROJECT_ID", "p")
    monkeypatch.setenv("CREDIT_KNOWLEDGE_DATA_STORE_ID", "credit-knowledge")
    monkeypatch.setattr(importer, "apply_schema", lambda *a: calls.append("schema"))
    monkeypatch.setattr(importer, "import_snapshot", lambda *a: calls.append("import"))
    monkeypatch.setattr(importer, "prune_documents", lambda *a: calls.append("prune"))
    monkeypatch.setattr(discoveryengine, "SchemaServiceClient", lambda: None)
    monkeypatch.setattr(discoveryengine, "DocumentServiceClient", lambda: None)
    assert importer.main() == 0
    assert calls == ["schema", "import", "prune"]


@pytest.mark.parametrize("client", [FakeDocumentClient(failure_count=1), FakeDocumentClient(error_messages=["bad"])])
def test_import_failure_exits_non_zero(client):
    with pytest.raises(RuntimeError, match="import failed"):
        importer.import_snapshot(client, STORE, load_corpus())


def test_import_refuses_snapshots_beyond_one_inline_request():
    corpus = load_corpus()
    big = CorpusSnapshot(corpus.manifest, tuple(corpus.records) * 2)
    with pytest.raises(ValueError, match="inline import allows"):
        importer.import_snapshot(FakeDocumentClient(), STORE, big)


def test_import_requires_project_and_store():
    with pytest.raises(ValueError):
        importer.data_store_name({"CREDIT_KNOWLEDGE_PROJECT_ID": "p"})
    assert importer.data_store_name(
        {"CREDIT_KNOWLEDGE_PROJECT_ID": "p", "CREDIT_KNOWLEDGE_DATA_STORE_ID": "credit-knowledge"}
    ) == STORE
    assert json.dumps(importer.corpus_json_schema())  # serializable
