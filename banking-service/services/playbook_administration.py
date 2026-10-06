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

"""Bank-owned draft editing, validation, publication and management evidence.

Change-request title and description are bounded operator metadata stored with the
change request. Like raw draft text, they never enter the ordinary audit stream;
audit events carry identifiers, versions and the effective publication policy.
"""

from copy import deepcopy
import datetime
import json
import re
import unicodedata
import uuid
from models.playbook import CHANGE_REQUEST_DESCRIPTION_MAX, CHANGE_REQUEST_TITLE_MAX
from services.playbook_repository import (
    SqlPlaybookRepository,
    RepositoryError,
    PlaybookConflict,
)
from services.playbook_policy import PublishPolicy
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
TITLE_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f]")
DESCRIPTION_FORBIDDEN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def has_format_characters(text):
    # Category Cf covers bidi overrides/isolates and zero-width characters that can
    # make a rendered title or description read differently from its stored value.
    return any(unicodedata.category(character) == "Cf" for character in text)


def bounded_change_request_text(title, description):
    if title is not None:
        title = title.strip()
        if (
            not 1 <= len(title) <= CHANGE_REQUEST_TITLE_MAX
            or TITLE_FORBIDDEN.search(title)
            or has_format_characters(title)
        ):
            raise RepositoryError(
                f"Change request title must be 1-{CHANGE_REQUEST_TITLE_MAX} printable characters."
            )
    if description is not None and (
        len(description) > CHANGE_REQUEST_DESCRIPTION_MAX
        or DESCRIPTION_FORBIDDEN.search(description)
        or has_format_characters(description)
    ):
        raise RepositoryError(
            f"Change request description must be at most {CHANGE_REQUEST_DESCRIPTION_MAX} characters of text."
        )
    return title, description


def structural_diff(before, after):
    """JSON-pointer changes; a missing key differs from an explicit null."""
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


def operation_contract(operation):
    return dict(
        parameters=deepcopy(operation.parameters),
        literal_bindings=deepcopy(operation.literal_bindings),
        required_facts=sorted(operation.required_facts),
        public_fields=sorted(operation.public_fields),
        template_fields=sorted(operation.template_fields),
        payload_fields=sorted(operation.payload_schema),
    )


def revision_metadata(view):
    change_request = view.get("change_request") or {}
    return dict(
        playbook_id=view["id"],
        revision=view["revision"],
        digest=view["digest"],
        draft_version=view["draft_version"],
        generation=view["generation"],
        base_revision=view.get("base_revision"),
        change_request_id=change_request.get("id"),
        origin=change_request.get("origin"),
    )


def change_request_metadata(view):
    return dict(
        playbook_id=view["playbook_id"],
        change_request_id=view["id"],
        revision=view["revision"],
        status=view["status"],
        version=view["version"],
    )


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
    def __init__(self, db, *, repository=None, clock=None, policy=None):
        self.db = db
        self.repository = repository or SqlPlaybookRepository(db)
        self.clock = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))
        # Read per service instance (per request) so deployment changes apply without code.
        self.policy = policy or PublishPolicy.from_env()

    def list(self):
        return {"playbooks": self.repository.list()}

    def get(self, playbook_id, revision):
        return self.repository.get(playbook_id, revision)

    def policy_view(self):
        return self.policy.view()

    def capabilities(self):
        # Code-owned examples describe only registered bounded execution capabilities.
        templates = {}
        for document in bundled_documents():
            if document.get("schema_version") == 2:
                templates[document["operation"]] = validate_definition(document)
        bound = {}
        for playbook in self.repository.list():
            bound.setdefault(playbook["operation"], []).append(
                {
                    key: playbook[key]
                    for key in ("id", "action_type", "published_revision")
                }
            )
        return {
            "operations": [
                dict(
                    operation=key,
                    input_schema=input_schema(operation),
                    template=deepcopy(templates[key]),
                    contract=operation_contract(operation),
                    bound_playbooks=bound.get(key, []),
                )
                for key, operation in sorted(OPERATIONS.items())
                if key in templates
            ]
        }

    def _change(
        self,
        event,
        actor,
        operation,
        *,
        describe=revision_metadata,
        evidence=False,
        follow_on=None,
    ):
        try:
            view = operation(self.clock())
            event_id = str(uuid.uuid4())
            actor_ref = stable_log_reference(actor, "operator")
            payload = dict(
                management_contract="playbook-management.v1",
                actor_ref=actor_ref,
                **describe(view),
            )
            if evidence:
                publish_policy = self.policy.audit_view()
                payload["previous_published"] = view.pop("previous_published", None)
                payload["publish_policy"] = publish_policy
                payload["evidence_artifact"] = archive(
                    self.db,
                    event_id,
                    {
                        "kind": "PLAYBOOK_PUBLICATION",
                        "definition": view["document"],
                        "definition_digest": view["digest"],
                        "change_request_id": payload["change_request_id"],
                        "publish_policy": publish_policy,
                    },
                    recorder=record_audit_event,
                )
            record_audit_event(self.db, event, payload, event_id=event_id)
            # Follow-on lifecycle events commit (or roll back) with the primary change.
            for follow_event, follow_payload in (follow_on(view) if follow_on else []):
                record_audit_event(
                    self.db,
                    follow_event,
                    dict(
                        management_contract="playbook-management.v1",
                        actor_ref=actor_ref,
                        **follow_payload,
                    ),
                    event_id=str(uuid.uuid4()),
                )
            self.db.commit()
            return view
        except Exception:
            self.db.rollback()
            raise

    def create(self, document, actor, title=None, description=None):
        document = bounded_document(document)
        if document["revision"] != 1:
            raise RepositoryError("New playbooks start at revision 1.")
        title, description = bounded_change_request_text(title, description)
        return self._change(
            "PLAYBOOK_DRAFT_CREATED",
            actor,
            lambda now: self.repository.create(
                document, actor, now, title=title, description=description or ""
            ),
        )

    def create_draft(
        self,
        playbook_id,
        source_revision,
        expected_generation,
        actor,
        title=None,
        description=None,
    ):
        title, description = bounded_change_request_text(title, description)
        return self._change(
            "PLAYBOOK_DRAFT_CREATED",
            actor,
            lambda now: self.repository.create_draft(
                playbook_id,
                source_revision,
                expected_generation,
                actor,
                now,
                title=title,
                description=description or "",
            ),
        )

    def restore(
        self,
        playbook_id,
        source_revision,
        expected_generation,
        actor,
        title=None,
        description=None,
    ):
        title, description = bounded_change_request_text(title, description)
        return self._change(
            "PLAYBOOK_DRAFT_CREATED",
            actor,
            lambda now: self.repository.restore(
                playbook_id,
                source_revision,
                expected_generation,
                actor,
                now,
                title=title,
                description=description or "",
            ),
            describe=lambda view: revision_metadata(view)
            | {"source_revision": source_revision},
        )

    def recreate_from_head(
        self,
        playbook_id,
        change_request_id,
        expected_draft_version,
        expected_generation,
        actor,
    ):
        return self._change(
            "PLAYBOOK_DRAFT_CREATED",
            actor,
            lambda now: self.repository.recreate_from_head(
                playbook_id,
                change_request_id,
                expected_draft_version,
                expected_generation,
                actor,
                now,
            ),
            describe=lambda view: revision_metadata(view)
            | {"superseded_change_request_id": change_request_id},
            follow_on=lambda view: [
                (
                    "PLAYBOOK_CHANGE_REQUEST_CLOSED",
                    change_request_metadata(
                        self.repository.change_request(playbook_id, change_request_id)
                    )
                    | {
                        "reason": "SUPERSEDED",
                        "superseded_by_change_request_id": view["change_request"]["id"],
                    },
                )
            ],
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

    @staticmethod
    def _validation(document):
        try:
            document = validate_definition(bounded_document(document))
            if document["schema_version"] != 2:
                raise RepositoryError(
                    "Published playbooks require schema 2 discovery metadata."
                )
            return {"valid": True, "errors": [], "digest": definition_digest(document)}
        except (ValueError, TypeError, KeyError) as exc:
            return {"valid": False, "errors": [str(exc)], "digest": None}

    def validate(self, playbook_id, revision, expected_draft_version):
        view = self.repository.get(playbook_id, revision)
        if view["status"] != "DRAFT" or view["draft_version"] != expected_draft_version:
            raise PlaybookConflict(
                "Draft changed or already published; refresh before validating."
            )
        return self._validation(view["document"])

    def publish(
        self, playbook_id, revision, expected_draft_version, expected_generation, actor
    ):
        def operation(now):
            # Phase 1 supports direct publication only; anything else fails closed.
            self.policy.require_direct_publish()
            # Lock the publication head before loading the draft or validating its exact bytes.
            self.repository.lock(playbook_id)
            previous_revision = self.repository.head(playbook_id)["published_revision"]
            self.repository.publishable(playbook_id, revision)
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

    def change_requests(self, playbook_id, status=None):
        return {"change_requests": self.repository.change_requests(playbook_id, status)}

    def change_request_detail(self, playbook_id, change_request_id):
        change_request = self.repository.change_request(playbook_id, change_request_id)
        head = self.repository.head(playbook_id)
        draft = self.repository.get(playbook_id, change_request["revision"])

        def revision(number):
            return (
                self.repository.get(playbook_id, number) if number is not None else None
            )

        base = revision(change_request["base_revision"])
        published = revision(head["published_revision"])
        current = published["document"] if published else None
        is_open = change_request["status"] == "OPEN"
        return dict(
            change_request=change_request,
            draft=draft,
            base=base,
            head=dict(
                published_revision=head["published_revision"],
                generation=head["generation"],
                digest=published["digest"] if published else None,
            ),
            diff_vs_base=structural_diff(base["document"], draft["document"])
            if base
            else None,
            diff_vs_head=structural_diff(current, draft["document"])
            if current is not None
            else None,
            upstream_changes=self._upstream_changes(change_request, head, current)
            if is_open
            else None,
            validation=self._validation(draft["document"]) if is_open else None,
        )

    def _upstream_changes(self, change_request, head, current):
        """Published changes since the revision this draft's content was derived from.

        Restored and recreated drafts copy older content onto the current head; the
        caller compares these paths with diff_vs_head to warn about silent reverts.
        """
        reference = (
            change_request["previous_base_revision"]
            if change_request["origin"] in ("RESTORE", "RECREATE")
            else change_request["base_revision"]
        )
        if current is None or reference == head["published_revision"]:
            return None
        before = (
            self.repository.get(change_request["playbook_id"], reference)["document"]
            if reference is not None
            else {}
        )
        return dict(
            from_revision=reference,
            to_revision=head["published_revision"],
            changes=structural_diff(before, current)["changes"],
        )

    def update_change_request(
        self,
        playbook_id,
        change_request_id,
        expected_version,
        actor,
        title=None,
        description=None,
    ):
        title, description = bounded_change_request_text(title, description)
        if title is None and description is None:
            raise RepositoryError("Provide a title or description to update.")
        return self._change(
            "PLAYBOOK_CHANGE_REQUEST_UPDATED",
            actor,
            lambda now: self.repository.update_change_request(
                playbook_id,
                change_request_id,
                expected_version,
                title=title,
                description=description,
            ),
            describe=change_request_metadata,
        )

    def close_change_request(self, playbook_id, change_request_id, actor):
        return self._change(
            "PLAYBOOK_CHANGE_REQUEST_CLOSED",
            actor,
            lambda now: self.repository.close_change_request(
                playbook_id, change_request_id, actor, now
            ),
            describe=change_request_metadata,
        )

    def history(self, playbook_id):
        return {"revisions": self.repository.history(playbook_id)}

    def compare(self, playbook_id, from_revision, to_revision):
        before = self.repository.get(playbook_id, from_revision)["document"]
        after = self.repository.get(playbook_id, to_revision)["document"]
        return structural_diff(before, after)
