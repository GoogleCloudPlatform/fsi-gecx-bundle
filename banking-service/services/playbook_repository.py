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

"""Versioned storage contract and SQL/memory adapters.

Callers authorize and validate documents before writes. Reads return detached copies.
Writes belong to the caller transaction and never commit; service writes and audit
therefore commit together. Missing identity precedes version conflict. Head generations
serialize revision allocation/publication, draft versions reject lost edits. Published
revisions cannot be edited or deleted. Snapshots include all published history plus
explicit current heads, never drafts. SQL heads are locked until caller transaction ends.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from sqlalchemy import select, update, func, and_
from sqlalchemy.exc import IntegrityError
from models.playbook import Playbook, PlaybookRevision


class RepositoryError(ValueError):
    code = "PLAYBOOK_INVALID"


class PlaybookNotFound(RepositoryError):
    code = "PLAYBOOK_NOT_FOUND"


class PlaybookConflict(RepositoryError):
    code = "PLAYBOOK_CONFLICT"


@dataclass(frozen=True)
class CatalogSnapshot:
    documents: tuple[dict, ...]
    published: frozenset[tuple[str, int]]


class PlaybookRepository(Protocol):
    def snapshot(self) -> CatalogSnapshot: ...
    def list(self) -> list[dict]: ...
    def get(self, playbook_id: str, revision: int) -> dict: ...
    def create(self, document: dict, actor: str, now: datetime) -> dict: ...
    def create_draft(
        self,
        playbook_id: str,
        source_revision: int,
        expected_generation: int,
        actor: str,
        now: datetime,
    ) -> dict: ...
    def edit(
        self,
        playbook_id: str,
        revision: int,
        document: dict,
        expected_draft_version: int,
        actor: str,
        now: datetime,
    ) -> dict: ...
    def publish(
        self,
        playbook_id: str,
        revision: int,
        digest: str,
        expected_draft_version: int,
        expected_generation: int,
        actor: str,
        now: datetime,
    ) -> dict: ...
    def lock(self, playbook_id: str) -> int: ...
    def lock_published(self, playbook_id: str) -> tuple[int, str]: ...


def revision_view(row, generation):
    def timestamp(value):
        return (
            value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        ).isoformat()

    return dict(
        id=row.playbook_id,
        revision=row.revision,
        status=row.status,
        digest=row.digest,
        draft_version=row.draft_version,
        generation=generation,
        document=deepcopy(row.document),
        created_by=row.created_by,
        updated_by=row.updated_by,
        created_at=timestamp(row.created_at),
        updated_at=timestamp(row.updated_at),
        published_at=timestamp(row.published_at) if row.published_at else None,
    )


class SqlPlaybookRepository:
    def __init__(self, db):
        self.db = db

    def _head(self, playbook_id, *, lock=False):
        query = (
            select(Playbook)
            .where(Playbook.id == playbook_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        head = self.db.execute(query).scalar_one_or_none()
        if head is None:
            raise PlaybookNotFound("Playbook not found.")
        return head

    def _row(self, playbook_id, revision):
        row = self.db.execute(
            select(PlaybookRevision)
            .where(
                PlaybookRevision.playbook_id == playbook_id,
                PlaybookRevision.revision == revision,
            )
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if row is None:
            raise PlaybookNotFound("Playbook revision not found.")
        return row

    def snapshot(self):
        # A single statement supplies history and head identities from one MVCC snapshot.
        rows = self.db.execute(
            select(PlaybookRevision, Playbook)
            .select_from(Playbook)
            .outerjoin(
                PlaybookRevision,
                and_(
                    Playbook.id == PlaybookRevision.playbook_id,
                    PlaybookRevision.status == "PUBLISHED",
                ),
            )
            .execution_options(populate_existing=True)
        ).all()
        from services.proposal_definitions import definition_digest

        available = {
            (row.playbook_id, row.revision) for row, _ in rows if row is not None
        }
        for row, head in rows:
            if (
                head.published_revision is not None
                and (head.id, head.published_revision) not in available
            ):
                raise RepositoryError(
                    "Published playbook head is unavailable or invalid."
                )
            if row is None:
                continue
            if (
                row.document.get("id") != row.playbook_id
                or row.document.get("revision") != row.revision
                or row.document.get("action_type") != head.action_type
                or row.document.get("contract_version") != head.contract_version
                or row.document.get("operation") != head.operation
                or definition_digest(row.document) != row.digest
            ):
                raise RepositoryError(
                    "Published playbook snapshot identity is invalid."
                )
        return CatalogSnapshot(
            tuple(deepcopy(r.document) for r, _ in rows if r is not None),
            frozenset(
                (r.playbook_id, r.revision)
                for r, head in rows
                if r is not None and r.revision == head.published_revision
            ),
        )

    def list(self):
        rows = self.db.execute(
            select(Playbook, PlaybookRevision)
            .outerjoin(PlaybookRevision, PlaybookRevision.playbook_id == Playbook.id)
            .order_by(Playbook.id, PlaybookRevision.revision)
            .execution_options(populate_existing=True)
        ).all()
        result = {}
        for head, row in rows:
            entry = result.setdefault(
                head.id,
                dict(
                    id=head.id,
                    action_type=head.action_type,
                    contract_version=head.contract_version,
                    published_revision=head.published_revision,
                    generation=head.generation,
                    revisions=[],
                ),
            )
            if row:
                view = revision_view(row, head.generation)
                entry["revisions"].append(
                    {
                        k: view[k]
                        for k in (
                            "revision",
                            "status",
                            "digest",
                            "draft_version",
                            "updated_at",
                        )
                    }
                )
        return list(result.values())

    def get(self, playbook_id, revision):
        head = self._head(playbook_id)
        return revision_view(self._row(playbook_id, revision), head.generation)

    def create(self, document, actor, now):
        head = Playbook(
            id=document["id"],
            action_type=document["action_type"],
            contract_version=document["contract_version"],
            operation=document["operation"],
            generation=1,
        )
        row = PlaybookRevision(
            playbook_id=head.id,
            revision=1,
            status="DRAFT",
            document=deepcopy(document),
            draft_version=1,
            created_by=actor,
            updated_by=actor,
            created_at=now,
            updated_at=now,
        )
        self.db.add_all([head, row])
        try:
            self.db.flush()
        except IntegrityError as exc:
            raise PlaybookConflict(
                "Playbook id or action type already exists."
            ) from exc
        return revision_view(row, head.generation)

    def _generation(self, head, expected):
        # CAS works on SQLite too, where FOR UPDATE is unsupported.
        changed = self.db.execute(
            update(Playbook)
            .where(Playbook.id == head.id, Playbook.generation == expected)
            .values(generation=expected + 1)
            .execution_options(synchronize_session=False)
        ).rowcount
        if changed != 1:
            raise PlaybookConflict("The playbook changed; refresh before continuing.")
        head.generation = expected + 1

    def create_draft(
        self, playbook_id, source_revision, expected_generation, actor, now
    ):
        head = self._head(playbook_id, lock=True)
        source = self._row(playbook_id, source_revision)
        self._generation(head, expected_generation)
        revision = (
            self.db.execute(
                select(func.max(PlaybookRevision.revision)).where(
                    PlaybookRevision.playbook_id == playbook_id
                )
            ).scalar_one()
            + 1
        )
        document = deepcopy(source.document)
        document["revision"] = revision
        row = PlaybookRevision(
            playbook_id=playbook_id,
            revision=revision,
            status="DRAFT",
            document=document,
            draft_version=1,
            created_by=actor,
            updated_by=actor,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()
        return revision_view(row, head.generation)

    def edit(self, playbook_id, revision, document, expected_draft_version, actor, now):
        head = self._head(playbook_id, lock=True)
        row = self._row(playbook_id, revision)
        self._draft(row, expected_draft_version)
        for field in ("id", "revision", "action_type", "contract_version", "operation"):
            if document.get(field) != row.document.get(field):
                raise RepositoryError(
                    "Definition identity and capability are immutable."
                )
        changed = self.db.execute(
            update(PlaybookRevision)
            .where(
                PlaybookRevision.playbook_id == playbook_id,
                PlaybookRevision.revision == revision,
                PlaybookRevision.status == "DRAFT",
                PlaybookRevision.draft_version == expected_draft_version,
            )
            .values(
                document=deepcopy(document),
                draft_version=expected_draft_version + 1,
                updated_by=actor,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        ).rowcount
        if changed != 1:
            raise PlaybookConflict("Draft changed; refresh before editing.")
        self.db.expire(row)
        return revision_view(row, head.generation)

    @staticmethod
    def _draft(row, expected):
        if row.status != "DRAFT" or row.draft_version != expected:
            raise PlaybookConflict(
                "Draft changed or already published; refresh before continuing."
            )

    def publish(
        self,
        playbook_id,
        revision,
        digest,
        expected_draft_version,
        expected_generation,
        actor,
        now,
    ):
        head = self._head(playbook_id, lock=True)
        row = self._row(playbook_id, revision)
        self._draft(row, expected_draft_version)
        self._generation(head, expected_generation)
        row.status, row.digest, row.published_at = "PUBLISHED", digest, now
        row.updated_by, row.updated_at = actor, now
        head.published_revision = revision
        self.db.flush()
        return revision_view(row, head.generation)

    def lock(self, playbook_id):
        return self._head(playbook_id, lock=True).generation

    def lock_published(self, playbook_id):
        head = self._head(playbook_id, lock=True)
        if head.published_revision is None:
            raise PlaybookNotFound("No published playbook revision.")
        row = self._row(playbook_id, head.published_revision)
        return row.revision, row.digest


def bootstrap_catalog(db, documents, *, now, actor="bundle-bootstrap"):
    """Explicit initialization only. Never alter a populated operational repository."""
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy import text

        db.execute(text("SELECT pg_advisory_xact_lock(827341985003)"))
    if db.execute(select(Playbook.id).limit(1)).first():
        return
    from services.proposal_definitions import validate_definition, definition_digest

    groups = {}
    for document in documents:
        document = validate_definition(document)
        groups.setdefault(document["id"], []).append(document)
    for playbook_id, versions in groups.items():
        latest = max(versions, key=lambda d: d["revision"])
        db.add(
            Playbook(
                id=playbook_id,
                action_type=latest["action_type"],
                contract_version=latest["contract_version"],
                operation=latest["operation"],
                published_revision=latest["revision"],
                generation=1,
            )
        )
        db.flush()
        for document in versions:
            db.add(
                PlaybookRevision(
                    playbook_id=playbook_id,
                    revision=document["revision"],
                    status="PUBLISHED",
                    document=deepcopy(document),
                    digest=definition_digest(document),
                    draft_version=1,
                    created_by=actor,
                    updated_by=actor,
                    created_at=now,
                    updated_at=now,
                    published_at=now,
                )
            )
    db.flush()


class MemoryPlaybookRepository:
    """Independent detached-copy in-memory fake for contract consumers.

    Sequential transitions mirror SQL semantics. Transaction rollback is owned by
    the test/service unit of work; this fake deliberately performs no I/O.
    """

    def __init__(self):
        self.heads = {}
        self.revisions = {}

    def _head(self, playbook_id):
        if playbook_id not in self.heads:
            raise PlaybookNotFound("Playbook not found.")
        return self.heads[playbook_id]

    def get(self, playbook_id, revision):
        head = self._head(playbook_id)
        if (playbook_id, revision) not in self.revisions:
            raise PlaybookNotFound("Playbook revision not found.")
        return deepcopy(
            self.revisions[playbook_id, revision] | {"generation": head["generation"]}
        )

    def list(self):
        result = []
        for playbook_id, head in sorted(self.heads.items()):
            revisions = [
                self.get(playbook_id, revision)
                for pid, revision in sorted(self.revisions)
                if pid == playbook_id
            ]
            result.append(
                deepcopy(head)
                | {
                    "revisions": [
                        {
                            key: row[key]
                            for key in (
                                "revision",
                                "status",
                                "digest",
                                "draft_version",
                                "updated_at",
                            )
                        }
                        for row in revisions
                    ]
                }
            )
        return result

    def snapshot(self):
        published = [
            row for row in self.revisions.values() if row["status"] == "PUBLISHED"
        ]
        return CatalogSnapshot(
            tuple(deepcopy(row["document"]) for row in published),
            frozenset(
                (row["id"], row["revision"])
                for row in published
                if self.heads[row["id"]]["published_revision"] == row["revision"]
            ),
        )

    def _draft(self, document, actor, now):
        row = dict(
            id=document["id"],
            revision=document["revision"],
            status="DRAFT",
            digest=None,
            draft_version=1,
            document=deepcopy(document),
            created_by=actor,
            updated_by=actor,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            published_at=None,
        )
        self.revisions[row["id"], row["revision"]] = row
        return self.get(row["id"], row["revision"])

    def create(self, document, actor, now):
        if document["id"] in self.heads or any(
            h["action_type"] == document["action_type"] for h in self.heads.values()
        ):
            raise PlaybookConflict("Playbook id or action type already exists.")
        self.heads[document["id"]] = dict(
            id=document["id"],
            action_type=document["action_type"],
            contract_version=document["contract_version"],
            operation=document["operation"],
            generation=1,
            published_revision=None,
        )
        return self._draft(document, actor, now)

    def _generation(self, head, expected):
        if head["generation"] != expected:
            raise PlaybookConflict("The playbook changed; refresh before continuing.")
        head["generation"] += 1

    def create_draft(
        self, playbook_id, source_revision, expected_generation, actor, now
    ):
        head = self._head(playbook_id)
        document = self.get(playbook_id, source_revision)["document"]
        self._generation(head, expected_generation)
        document["revision"] = 1 + max(
            rev for pid, rev in self.revisions if pid == playbook_id
        )
        return self._draft(document, actor, now)

    def _editable(self, playbook_id, revision, expected):
        row = self.get(playbook_id, revision)
        if row["status"] != "DRAFT" or row["draft_version"] != expected:
            raise PlaybookConflict(
                "Draft changed or already published; refresh before continuing."
            )
        return self.revisions[playbook_id, revision]

    def edit(self, playbook_id, revision, document, expected_draft_version, actor, now):
        row = self._editable(playbook_id, revision, expected_draft_version)
        for field in ("id", "revision", "action_type", "contract_version", "operation"):
            if document.get(field) != row["document"].get(field):
                raise RepositoryError(
                    "Definition identity and capability are immutable."
                )
        row.update(
            document=deepcopy(document),
            draft_version=expected_draft_version + 1,
            updated_by=actor,
            updated_at=now.isoformat(),
        )
        return self.get(playbook_id, revision)

    def publish(
        self,
        playbook_id,
        revision,
        digest,
        expected_draft_version,
        expected_generation,
        actor,
        now,
    ):
        row = self._editable(playbook_id, revision, expected_draft_version)
        self._generation(self._head(playbook_id), expected_generation)
        row.update(
            status="PUBLISHED",
            digest=digest,
            published_at=now.isoformat(),
            updated_by=actor,
            updated_at=now.isoformat(),
        )
        self.heads[playbook_id]["published_revision"] = revision
        return self.get(playbook_id, revision)

    def lock(self, playbook_id):
        return self._head(playbook_id)["generation"]

    def lock_published(self, playbook_id):
        revision = self._head(playbook_id)["published_revision"]
        if revision is None:
            raise PlaybookNotFound("No published playbook revision.")
        row = self.get(playbook_id, revision)
        return revision, row["digest"]
