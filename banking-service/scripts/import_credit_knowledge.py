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

"""Load the shipped credit knowledge snapshot into its Discovery Engine data store.

Runs as the Cloud Run Job ``banking-credit-knowledge-import`` (identity
``credit-knowledge-import-sa``, the only identity allowed to write the store):

1. Make the data store ``default_schema`` declare the corpus fields (grounded
   fields retrievable, text fields searchable, ids indexable). Skipped when the
   current schema already matches.
2. Import every record inline with INCREMENTAL reconciliation (Discovery
   Engine rejects FULL for inline sources). Exits non-zero on any failed
   document.
3. Prune: list the branch and delete every document whose id is not in the
   snapshot, so the store holds exactly this snapshot. Pruning runs after the
   import, so searches never see an empty store. Exits non-zero if any delete
   fails. Re-running with the same snapshot deletes nothing.

Environment: CREDIT_KNOWLEDGE_PROJECT_ID, CREDIT_KNOWLEDGE_LOCATION (default
``global``), CREDIT_KNOWLEDGE_DATA_STORE_ID.
"""
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.credit_knowledge_corpus import (  # noqa: E402
    INDEXABLE_FIELDS,
    SEARCHABLE_FIELDS,
    STRUCT_FIELDS,
    CorpusSnapshot,
    load_corpus,
)

logger = logging.getLogger("import_credit_knowledge")

INLINE_IMPORT_LIMIT = 100
OPERATION_TIMEOUT_S = 900
LIST_PAGE_SIZE = 100


def corpus_json_schema() -> dict[str, Any]:
    """Every corpus field is retrievable, so results carry the grounded fields."""
    properties = {}
    for field in STRUCT_FIELDS:
        properties[field] = {
            "type": "string",
            "retrievable": True,
            "searchable": field in SEARCHABLE_FIELDS,
            "indexable": field in INDEXABLE_FIELDS,
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": properties,
    }


def _current_schema(schema_client, schema_name: str) -> dict[str, Any] | None:
    from google.api_core import exceptions as api_exceptions
    from google.cloud import discoveryengine_v1 as discoveryengine
    from google.protobuf import json_format

    try:
        current = schema_client.get_schema(name=schema_name)
    except api_exceptions.NotFound:
        return None
    if current.json_schema:
        return json.loads(current.json_schema)
    return json_format.MessageToDict(discoveryengine.Schema.pb(current)).get("structSchema")


def apply_schema(schema_client, data_store_name: str) -> bool:
    """Idempotently declare the corpus schema; returns True when it was updated."""
    from google.cloud import discoveryengine_v1 as discoveryengine

    desired = corpus_json_schema()
    schema_name = f"{data_store_name}/schemas/default_schema"
    current = _current_schema(schema_client, schema_name)
    fields = ",".join(sorted(desired["properties"]))
    if current is not None and current.get("properties") == desired["properties"]:
        logger.info("Credit knowledge schema already current fields=%s", fields)
        return False
    operation = schema_client.update_schema(
        request=discoveryengine.UpdateSchemaRequest(
            schema=discoveryengine.Schema(name=schema_name, json_schema=json.dumps(desired, sort_keys=True)),
            allow_missing=True,
        )
    )
    operation.result(timeout=OPERATION_TIMEOUT_S)
    logger.info("Applied credit knowledge schema fields=%s", fields)
    return True


def _branch(data_store_name: str) -> str:
    return f"{data_store_name}/branches/default_branch"


def import_snapshot(document_client, data_store_name: str, corpus: CorpusSnapshot) -> int:
    """Upsert every snapshot record in one INCREMENTAL inline request; returns the record count.

    Discovery Engine allows FULL reconciliation only for GCS/BigQuery sources;
    ``prune_documents`` removes records that are not in the snapshot.
    """
    from google.cloud import discoveryengine_v1 as discoveryengine

    if len(corpus.records) > INLINE_IMPORT_LIMIT:
        raise ValueError(
            f"Snapshot has {len(corpus.records)} records; inline import allows {INLINE_IMPORT_LIMIT}. "
            "Switch the import to a GCS source."
        )
    documents = [
        discoveryengine.Document(id=record["id"], struct_data=record["structData"])
        for record in corpus.records
    ]
    operation = document_client.import_documents(
        request=discoveryengine.ImportDocumentsRequest(
            parent=_branch(data_store_name),
            inline_source=discoveryengine.ImportDocumentsRequest.InlineSource(documents=documents),
            reconciliation_mode=discoveryengine.ImportDocumentsRequest.ReconciliationMode.INCREMENTAL,
        )
    )
    response = operation.result(timeout=OPERATION_TIMEOUT_S)
    metadata = operation.metadata
    failures = int(getattr(metadata, "failure_count", 0) or 0)
    if failures or list(response.error_samples):
        raise RuntimeError(
            f"Credit knowledge import failed for {failures} document(s); "
            f"first error: {response.error_samples[0].message if response.error_samples else 'unknown'}"
        )
    logger.info(
        "Imported credit knowledge snapshot snapshot_id=%s records=%d",
        corpus.snapshot_id,
        len(documents),
    )
    return len(documents)


def _stored_documents(document_client, data_store_name: str):
    from google.cloud import discoveryengine_v1 as discoveryengine

    page_token = ""
    while True:
        page = document_client.list_documents(
            request=discoveryengine.ListDocumentsRequest(
                parent=_branch(data_store_name), page_size=LIST_PAGE_SIZE, page_token=page_token
            )
        )
        yield from page.documents
        page_token = page.next_page_token
        if not page_token:
            return


def prune_documents(document_client, data_store_name: str, corpus: CorpusSnapshot) -> tuple[int, int]:
    """Delete stored documents whose id is not in the snapshot; returns (kept, deleted).

    Runs only after a successful import. Raises if any delete fails, after
    attempting the rest, so the job exits non-zero.
    """
    from google.api_core import exceptions as api_exceptions
    from google.cloud import discoveryengine_v1 as discoveryengine

    snapshot_ids = {record["id"] for record in corpus.records}
    if not snapshot_ids:
        raise ValueError("Refusing to prune against an empty snapshot.")
    stale = []
    kept = 0
    for document in _stored_documents(document_client, data_store_name):
        document_id = document.id or document.name.rsplit("/", 1)[-1]
        if document_id in snapshot_ids:
            kept += 1
        else:
            stale.append(document.name)
    deleted, failed = 0, 0
    for name in stale:
        try:
            document_client.delete_document(request=discoveryengine.DeleteDocumentRequest(name=name))
            deleted += 1
        except api_exceptions.NotFound:
            deleted += 1  # Already gone: the end state is what pruning wants.
        except api_exceptions.GoogleAPIError as exc:
            failed += 1
            logger.error("Credit knowledge prune delete failed error_type=%s", type(exc).__name__)
    logger.info(
        "Pruned credit knowledge store snapshot_id=%s kept=%d deleted=%d failed=%d",
        corpus.snapshot_id,
        kept,
        deleted,
        failed,
    )
    if failed:
        raise RuntimeError(f"Credit knowledge prune failed for {failed} document(s).")
    return kept, deleted


def data_store_name(environ: dict[str, str]) -> str:
    project = environ.get("CREDIT_KNOWLEDGE_PROJECT_ID", "").strip()
    store = environ.get("CREDIT_KNOWLEDGE_DATA_STORE_ID", "").strip()
    location = environ.get("CREDIT_KNOWLEDGE_LOCATION", "").strip() or "global"
    if not project or not store:
        raise ValueError("CREDIT_KNOWLEDGE_PROJECT_ID and CREDIT_KNOWLEDGE_DATA_STORE_ID are required.")
    return f"projects/{project}/locations/{location}/collections/default_collection/dataStores/{store}"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    from google.cloud import discoveryengine_v1 as discoveryengine

    name = data_store_name(dict(os.environ))
    corpus = load_corpus()
    apply_schema(discoveryengine.SchemaServiceClient(), name)
    document_client = discoveryengine.DocumentServiceClient()
    import_snapshot(document_client, name, corpus)
    prune_documents(document_client, name, corpus)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
