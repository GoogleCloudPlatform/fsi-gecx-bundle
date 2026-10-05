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

"""Bank-owned draft editing, validation, publication and management evidence."""

from copy import deepcopy
import datetime
import json
import re
import uuid
from services.playbook_repository import (
    SqlPlaybookRepository,
    RepositoryError,
    PlaybookConflict,
)
from services.proposal_definitions import (
    validate_definition,
    definition_digest,
    bundled_documents,
)
from services.proposal_capabilities import OPERATIONS
from services.playbook_discovery import input_schema
from services.proposal_evidence import archive
from utils.audit import record_audit_event
from utils.log_safety import stable_log_reference

MAX_DOCUMENT_BYTES = 65536


def bounded_document(document):
    if not isinstance(document, dict):
        raise RepositoryError("Definition must be a JSON object.")

    def depth(value, level=0):
        if level > 16:
            raise RepositoryError("Definition nesting exceeds 16 levels.")
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise RepositoryError("Definition keys must be strings.")
                depth(item, level + 1)
        elif isinstance(value, list):
            for item in value:
                depth(item, level + 1)
        elif value is not None and type(value) not in (str, int, float, bool):
            raise RepositoryError("Definition must contain only JSON values.")

    depth(document)
    try:
        encoded = json.dumps(document, allow_nan=False, separators=(",", ":"))
    except (ValueError, TypeError) as exc:
        raise RepositoryError("Definition must contain finite JSON values.") from exc
    if len(encoded.encode()) > MAX_DOCUMENT_BYTES:
        raise RepositoryError("Definition exceeds 64 KiB.")
    for field, limit in (
        ("id", 128),
        ("action_type", 64),
        ("contract_version", 32),
        ("operation", 128),
    ):
        value = document.get(field)
        if (
            not isinstance(value, str)
            or not 1 <= len(value) <= limit
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value)
        ):
            raise RepositoryError(f"Invalid definition {field}.")
    if type(document.get("revision")) is not int or document["revision"] < 1:
        raise RepositoryError("Definition revision must be a positive integer.")
    if document["operation"] not in OPERATIONS:
        raise RepositoryError("Unknown registered operation.")
    return deepcopy(document)


class PlaybookAdministration:
    def __init__(self, db, *, repository=None, clock=None):
        self.db = db
        self.repository = repository or SqlPlaybookRepository(db)
        self.clock = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))

    def list(self):
        return {"playbooks": self.repository.list()}

    def get(self, playbook_id, revision):
        return self.repository.get(playbook_id, revision)

    def capabilities(self):
        # Code-owned examples describe only registered bounded execution capabilities.
        templates = {}
        for document in bundled_documents():
            if document.get("schema_version") == 2:
                templates[document["operation"]] = validate_definition(document)
        return {
            "operations": [
                dict(
                    operation=key,
                    input_schema=input_schema(operation),
                    template=deepcopy(templates[key]),
                )
                for key, operation in sorted(OPERATIONS.items())
                if key in templates
            ]
        }

    def _change(self, event, actor, operation, *, evidence=False):
        try:
            view = operation(self.clock())
            event_id = str(uuid.uuid4())
            payload = dict(
                management_contract="playbook-management.v1",
                actor_ref=stable_log_reference(actor, "operator"),
                playbook_id=view["id"],
                revision=view["revision"],
                digest=view["digest"],
                draft_version=view["draft_version"],
                generation=view["generation"],
            )
            if evidence:
                payload["previous_published"] = view.pop("previous_published", None)
                payload["evidence_artifact"] = archive(
                    self.db,
                    event_id,
                    {
                        "kind": "PLAYBOOK_PUBLICATION",
                        "definition": view["document"],
                        "definition_digest": view["digest"],
                    },
                    recorder=record_audit_event,
                )
            record_audit_event(self.db, event, payload, event_id=event_id)
            self.db.commit()
            return view
        except Exception:
            self.db.rollback()
            raise

    def create(self, document, actor):
        document = bounded_document(document)
        if document["revision"] != 1:
            raise RepositoryError("New playbooks start at revision 1.")
        return self._change(
            "PLAYBOOK_DRAFT_CREATED",
            actor,
            lambda now: self.repository.create(document, actor, now),
        )

    def create_draft(self, playbook_id, source_revision, expected_generation, actor):
        return self._change(
            "PLAYBOOK_DRAFT_CREATED",
            actor,
            lambda now: self.repository.create_draft(
                playbook_id, source_revision, expected_generation, actor, now
            ),
        )

    def edit(self, playbook_id, revision, document, expected_draft_version, actor):
        document = bounded_document(document)
        original = self.repository.get(playbook_id, revision)
        for field in ("id", "revision", "action_type", "contract_version", "operation"):
            if document[field] != original["document"][field]:
                raise RepositoryError(
                    "Definition identity and action contract are immutable."
                )
        return self._change(
            "PLAYBOOK_DRAFT_EDITED",
            actor,
            lambda now: self.repository.edit(
                playbook_id, revision, document, expected_draft_version, actor, now
            ),
        )

    def validate(self, playbook_id, revision, expected_draft_version):
        view = self.repository.get(playbook_id, revision)
        if view["status"] != "DRAFT" or view["draft_version"] != expected_draft_version:
            raise PlaybookConflict(
                "Draft changed or already published; refresh before validating."
            )
        try:
            document = validate_definition(bounded_document(view["document"]))
            if document["schema_version"] != 2:
                raise RepositoryError(
                    "Published playbooks require schema 2 discovery metadata."
                )
            return {"valid": True, "errors": [], "digest": definition_digest(document)}
        except (ValueError, TypeError, KeyError) as exc:
            return {"valid": False, "errors": [str(exc)], "digest": None}

    def publish(
        self, playbook_id, revision, expected_draft_version, expected_generation, actor
    ):
        def operation(now):
            # Lock the publication head before loading the draft or validating its exact bytes.
            self.repository.lock(playbook_id)
            heads = self.repository.list()
            head = next(h for h in heads if h["id"] == playbook_id)
            previous_revision = head["published_revision"]
            previous = (
                self.repository.get(playbook_id, previous_revision)
                if previous_revision
                else None
            )
            validation = self.validate(playbook_id, revision, expected_draft_version)
            if not validation["valid"]:
                raise RepositoryError(validation["errors"][0])
            view = self.repository.publish(
                playbook_id,
                revision,
                validation["digest"],
                expected_draft_version,
                expected_generation,
                actor,
                now,
            )
            view["previous_published"] = (
                {"revision": previous["revision"], "digest": previous["digest"]}
                if previous
                else None
            )
            return view

        return self._change("PLAYBOOK_PUBLISHED", actor, operation, evidence=True)

    def compare(self, playbook_id, from_revision, to_revision):
        before = self.repository.get(playbook_id, from_revision)["document"]
        after = self.repository.get(playbook_id, to_revision)["document"]
        changes = []

        def compare(left, right, path):
            if isinstance(left, dict) and isinstance(right, dict):
                for key in sorted(set(left) | set(right)):
                    escaped = key.replace("~", "~0").replace("/", "~1")
                    child_path = path + "/" + escaped
                    if key not in left or key not in right:
                        changes.append(
                            dict(
                                path=child_path,
                                before=left.get(key),
                                after=right.get(key),
                                change_type="ADDED" if key not in left else "REMOVED",
                            )
                        )
                    else:
                        compare(left[key], right[key], child_path)
            elif left != right:
                changes.append(
                    dict(path=path, before=left, after=right, change_type="CHANGED")
                )

        compare(before, after, "")
        return {"changes": changes}
