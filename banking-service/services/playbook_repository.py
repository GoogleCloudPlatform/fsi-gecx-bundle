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

Change requests: every draft revision is allocated together with exactly one change
request whose base is the published head at allocation time (NULL without a head).
Only OPEN change requests may be edited, retitled, closed or published; PUBLISHED and
CLOSED are final. New drafts start from the published head; history is restored
explicitly. Publication error order: playbook missing, change request not OPEN,
base behind the head (BEHIND_HEAD), stale draft version, stale generation.
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from sqlalchemy import select, update, func, and_
from sqlalchemy.exc import IntegrityError
from models.playbook import Playbook, PlaybookRevision, PlaybookChangeRequest


class RepositoryError(ValueError):
    code = "PLAYBOOK_INVALID"


class PlaybookNotFound(RepositoryError):
    code = "PLAYBOOK_NOT_FOUND"


class PlaybookConflict(RepositoryError):
    code = "PLAYBOOK_CONFLICT"


class ChangeRequestNotFound(PlaybookNotFound):
    code = "CHANGE_REQUEST_NOT_FOUND"


class ChangeRequestNotOpen(PlaybookConflict):
    code = "CHANGE_REQUEST_NOT_OPEN"


class BehindHead(PlaybookConflict):
    code = "BEHIND_HEAD"


class NotBehindHead(PlaybookConflict):
    code = "NOT_BEHIND"


@dataclass(frozen=True)
class CatalogSnapshot:
    documents: tuple[dict, ...]
    published: frozenset[tuple[str, int]]


class PlaybookRepository(Protocol):
    def snapshot(self) -> CatalogSnapshot: ...
    def list(self) -> list[dict]: ...
    def head(self, playbook_id: str) -> dict: ...
    def get(self, playbook_id: str, revision: int) -> dict: ...
    def create(
        self,
        document: dict,
        actor: str,
        now: datetime,
        *,
        title: str | None = None,
        description: str = "",
    ) -> dict: ...
    def create_draft(
        self,
        playbook_id: str,
        source_revision: int,
        expected_generation: int,
        actor: str,
        now: datetime,
        *,
        title: str | None = None,
        description: str = "",
    ) -> dict: ...
    def restore(
        self,
        playbook_id: str,
        source_revision: int,
        expected_generation: int,
        actor: str,
        now: datetime,
        *,
        title: str | None = None,
        description: str = "",
    ) -> dict: ...
    def recreate_from_head(
        self,
        playbook_id: str,
        change_request_id: int,
        expected_draft_version: int,
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
    def publishable(self, playbook_id: str, revision: int) -> dict: ...
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
    def change_requests(
        self, playbook_id: str, status: str | None = None
    ) -> "list[dict]": ...
    def change_request(self, playbook_id: str, change_request_id: int) -> dict: ...
    def update_change_request(
        self,
        playbook_id: str,
        change_request_id: int,
        expected_version: int,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> dict: ...
    def close_change_request(
        self, playbook_id: str, change_request_id: int, actor: str, now: datetime
    ) -> dict: ...
    def history(self, playbook_id: str) -> "list[dict]": ...
    def lock(self, playbook_id: str) -> int: ...
    def lock_published(self, playbook_id: str) -> tuple[int, str]: ...


def timestamp(value):
    return (
        value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    ).isoformat()


def revision_view(row, generation):
    return dict(
        id=row.playbook_id,
        revision=row.revision,
        status=row.status,
        digest=row.digest,
        draft_version=row.draft_version,
        generation=generation,
        base_revision=row.base_revision,
        document=deepcopy(row.document),
        created_by=row.created_by,
        updated_by=row.updated_by,
        created_at=timestamp(row.created_at),
        updated_at=timestamp(row.updated_at),
        published_at=timestamp(row.published_at) if row.published_at else None,
    )


def default_title(origin, playbook_id, source_revision=None):
    if origin == "CREATE":
        return f"Create {playbook_id}"
    if origin == "RESTORE":
        return f"Restore revision {source_revision}"
    return f"Update {playbook_id}"


CHANGE_REQUEST_FIELDS = (
    "id",
    "playbook_id",
    "revision",
    "base_revision",
    "origin",
    "previous_base_revision",
    "title",
    "description",
    "status",
    "version",
    "opened_by",
    "opened_at",
    "closed_by",
    "closed_at",
    "published_revision",
)


def change_request_view(fields, draft, head_published, published_revisions):
    """Project a change request; behind is relative to the current published head."""
    behind = fields["status"] == "OPEN" and fields["base_revision"] != head_published
    view = {key: fields[key] for key in CHANGE_REQUEST_FIELDS}
    view.update(
        behind=behind,
        behind_by=sum(
            1 for rev in published_revisions if rev > (fields["base_revision"] or 0)
        )
        if behind
        else 0,
        draft_version=draft["draft_version"],
        updated_by=draft["updated_by"],
        updated_at=draft["updated_at"],
    )
    return view


def change_request_fields(row):
    fields = {key: getattr(row, key) for key in CHANGE_REQUEST_FIELDS}
    for key in ("opened_at", "closed_at"):
        fields[key] = timestamp(fields[key]) if fields[key] else None
    return fields


def behind_message(base, head):
    return (
        f"This change request is based on revision {base or 'none'}, but revision "
        f"{head} is now published. Start a new change request from the current revision."
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
        open_counts = dict(
            self.db.execute(
                select(PlaybookChangeRequest.playbook_id, func.count())
                .where(PlaybookChangeRequest.status == "OPEN")
                .group_by(PlaybookChangeRequest.playbook_id)
            ).all()
        )
        result = {}
        for head, row in rows:
            entry = result.setdefault(
                head.id,
                dict(
                    id=head.id,
                    action_type=head.action_type,
                    contract_version=head.contract_version,
                    operation=head.operation,
                    published_revision=head.published_revision,
                    generation=head.generation,
                    open_change_requests=open_counts.get(head.id, 0),
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
                            "base_revision",
                            "updated_at",
                        )
                    }
                )
        return list(result.values())

    def head(self, playbook_id):
        head = self._head(playbook_id)
        return dict(
            id=head.id,
            action_type=head.action_type,
            contract_version=head.contract_version,
            operation=head.operation,
            published_revision=head.published_revision,
            generation=head.generation,
        )

    def get(self, playbook_id, revision):
        head = self._head(playbook_id)
        return revision_view(self._row(playbook_id, revision), head.generation)

    def create(self, document, actor, now, *, title=None, description=""):
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
            base_revision=None,
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
        return self._open(
            head,
            row,
            "CREATE",
            None,
            title or default_title("CREATE", head.id),
            description,
            actor,
            now,
        )

    def _published_revisions(self, playbook_id):
        return set(
            self.db.execute(
                select(PlaybookRevision.revision).where(
                    PlaybookRevision.playbook_id == playbook_id,
                    PlaybookRevision.status == "PUBLISHED",
                )
            ).scalars()
        )

    def _cr_view(self, cr, head):
        draft = revision_view(self._row(cr.playbook_id, cr.revision), head.generation)
        return change_request_view(
            change_request_fields(cr),
            draft,
            head.published_revision,
            self._published_revisions(cr.playbook_id),
        )

    def _cr_row(self, playbook_id, change_request_id):
        cr = self.db.execute(
            select(PlaybookChangeRequest)
            .where(
                PlaybookChangeRequest.id == change_request_id,
                PlaybookChangeRequest.playbook_id == playbook_id,
            )
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if cr is None:
            raise ChangeRequestNotFound("Change request not found.")
        return cr

    def _open_cr_for(self, playbook_id, revision):
        cr = self.db.execute(
            select(PlaybookChangeRequest)
            .where(
                PlaybookChangeRequest.playbook_id == playbook_id,
                PlaybookChangeRequest.revision == revision,
            )
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if cr is None or cr.status != "OPEN":
            raise ChangeRequestNotOpen(
                "This draft has no open change request; it cannot be changed or published."
            )
        return cr

    def _allocate(self, head, source_document, actor, now):
        revision = (
            self.db.execute(
                select(func.max(PlaybookRevision.revision)).where(
                    PlaybookRevision.playbook_id == head.id
                )
            ).scalar_one()
            + 1
        )
        document = deepcopy(source_document)
        document["revision"] = revision
        row = PlaybookRevision(
            playbook_id=head.id,
            revision=revision,
            status="DRAFT",
            document=document,
            draft_version=1,
            base_revision=head.published_revision,
            created_by=actor,
            updated_by=actor,
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _open(
        self, head, row, origin, previous_base, title, description, actor, now
    ):
        cr = PlaybookChangeRequest(
            playbook_id=head.id,
            revision=row.revision,
            base_revision=row.base_revision,
            origin=origin,
            previous_base_revision=previous_base,
            title=title,
            description=description or "",
            status="OPEN",
            version=1,
            opened_by=actor,
            opened_at=now,
        )
        self.db.add(cr)
        self.db.flush()
        view = revision_view(row, head.generation)
        view["change_request"] = self._cr_view(cr, head)
        return view

    def _finish(self, cr, status, actor, now):
        changed = self.db.execute(
            update(PlaybookChangeRequest)
            .where(
                PlaybookChangeRequest.id == cr.id,
                PlaybookChangeRequest.status == "OPEN",
            )
            .values(
                status=status,
                closed_by=actor,
                closed_at=now,
                published_revision=cr.revision if status == "PUBLISHED" else None,
                version=PlaybookChangeRequest.version + 1,
            )
            .execution_options(synchronize_session=False)
        ).rowcount
        if changed != 1:
            raise ChangeRequestNotOpen(
                "The change request is no longer open; refresh before continuing."
            )
        self.db.expire(cr)

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
        self,
        playbook_id,
        source_revision,
        expected_generation,
        actor,
        now,
        *,
        title=None,
        description="",
    ):
        head = self._head(playbook_id, lock=True)
        source = self._row(playbook_id, source_revision)
        if head.published_revision not in (None, source_revision):
            raise PlaybookConflict(
                "New change requests start from the published revision; "
                "restore historical revisions explicitly."
            )
        self._generation(head, expected_generation)
        row = self._allocate(head, source.document, actor, now)
        return self._open(
            head,
            row,
            "DRAFT",
            None,
            title or default_title("DRAFT", playbook_id),
            description,
            actor,
            now,
        )

    def restore(
        self,
        playbook_id,
        source_revision,
        expected_generation,
        actor,
        now,
        *,
        title=None,
        description="",
    ):
        head = self._head(playbook_id, lock=True)
        source = self._row(playbook_id, source_revision)
        if source.status != "PUBLISHED":
            raise PlaybookConflict("Only published revisions can be restored.")
        self._generation(head, expected_generation)
        row = self._allocate(head, source.document, actor, now)
        return self._open(
            head,
            row,
            "RESTORE",
            source_revision,
            title or default_title("RESTORE", playbook_id, source_revision),
            description,
            actor,
            now,
        )

    def recreate_from_head(
        self,
        playbook_id,
        change_request_id,
        expected_draft_version,
        expected_generation,
        actor,
        now,
    ):
        head = self._head(playbook_id, lock=True)
        old = self._cr_row(playbook_id, change_request_id)
        if old.status != "OPEN":
            raise ChangeRequestNotOpen("The change request is no longer open.")
        draft = self._row(playbook_id, old.revision)
        self._draft(draft, expected_draft_version)
        if old.base_revision == head.published_revision:
            raise NotBehindHead("The change request already targets the published revision.")
        self._generation(head, expected_generation)
        row = self._allocate(head, draft.document, actor, now)
        view = self._open(
            head,
            row,
            "RECREATE",
            old.base_revision,
            old.title,
            old.description,
            actor,
            now,
        )
        self._finish(old, "CLOSED", actor, now)
        return view

    def edit(self, playbook_id, revision, document, expected_draft_version, actor, now):
        head = self._head(playbook_id, lock=True)
        row = self._row(playbook_id, revision)
        cr = self._open_cr_for(playbook_id, revision)
        self._draft(row, expected_draft_version)
        for field in ("id", "revision", "action_type", "contract_version", "operation"):
            if document.get(field) != row.document.get(field):
                raise RepositoryError(
                    "Definition identity and capability are immutable."
                )
        open_change_request = (
            select(PlaybookChangeRequest.id)
            .where(
                PlaybookChangeRequest.playbook_id == playbook_id,
                PlaybookChangeRequest.revision == revision,
                PlaybookChangeRequest.status == "OPEN",
            )
            .exists()
        )
        changed = self.db.execute(
            update(PlaybookRevision)
            .where(
                PlaybookRevision.playbook_id == playbook_id,
                PlaybookRevision.revision == revision,
                PlaybookRevision.status == "DRAFT",
                PlaybookRevision.draft_version == expected_draft_version,
                open_change_request,
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
        view = revision_view(row, head.generation)
        view["change_request"] = self._cr_view(cr, head)
        return view

    @staticmethod
    def _draft(row, expected):
        if row.status != "DRAFT" or row.draft_version != expected:
            raise PlaybookConflict(
                "Draft changed or already published; refresh before continuing."
            )

    @staticmethod
    def _current_base(cr, head):
        if cr.base_revision != head.published_revision:
            raise BehindHead(behind_message(cr.base_revision, head.published_revision))

    def publishable(self, playbook_id, revision):
        head = self._head(playbook_id, lock=True)
        self._row(playbook_id, revision)
        cr = self._open_cr_for(playbook_id, revision)
        self._current_base(cr, head)
        return self._cr_view(cr, head)

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
        cr = self._open_cr_for(playbook_id, revision)
        self._current_base(cr, head)
        self._draft(row, expected_draft_version)
        self._generation(head, expected_generation)
        row.status, row.digest, row.published_at = "PUBLISHED", digest, now
        row.updated_by, row.updated_at = actor, now
        head.published_revision = revision
        self.db.flush()
        self._finish(cr, "PUBLISHED", actor, now)
        view = revision_view(row, head.generation)
        view["change_request"] = self._cr_view(cr, head)
        return view

    def change_requests(self, playbook_id, status=None):
        head = self._head(playbook_id)
        query = (
            select(PlaybookChangeRequest, PlaybookRevision)
            .join(
                PlaybookRevision,
                and_(
                    PlaybookRevision.playbook_id == PlaybookChangeRequest.playbook_id,
                    PlaybookRevision.revision == PlaybookChangeRequest.revision,
                ),
            )
            .where(PlaybookChangeRequest.playbook_id == playbook_id)
            .order_by(PlaybookChangeRequest.id.desc())
            .execution_options(populate_existing=True)
        )
        if status is not None:
            query = query.where(PlaybookChangeRequest.status == status)
        published = self._published_revisions(playbook_id)
        return [
            change_request_view(
                change_request_fields(cr),
                revision_view(draft, head.generation),
                head.published_revision,
                published,
            )
            for cr, draft in self.db.execute(query).all()
        ]

    def change_request(self, playbook_id, change_request_id):
        head = self._head(playbook_id)
        return self._cr_view(self._cr_row(playbook_id, change_request_id), head)

    def update_change_request(
        self,
        playbook_id,
        change_request_id,
        expected_version,
        *,
        title=None,
        description=None,
    ):
        head = self._head(playbook_id)
        cr = self._cr_row(playbook_id, change_request_id)
        if cr.status != "OPEN":
            raise ChangeRequestNotOpen("Only open change requests can be edited.")
        values = {"version": expected_version + 1}
        if title is not None:
            values["title"] = title
        if description is not None:
            values["description"] = description
        changed = self.db.execute(
            update(PlaybookChangeRequest)
            .where(
                PlaybookChangeRequest.id == cr.id,
                PlaybookChangeRequest.status == "OPEN",
                PlaybookChangeRequest.version == expected_version,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        ).rowcount
        if changed != 1:
            raise PlaybookConflict("Change request changed; refresh before editing.")
        self.db.expire(cr)
        return self._cr_view(cr, head)

    def close_change_request(self, playbook_id, change_request_id, actor, now):
        head = self._head(playbook_id)
        cr = self._cr_row(playbook_id, change_request_id)
        if cr.status != "OPEN":
            raise ChangeRequestNotOpen("Only open change requests can be closed.")
        self._finish(cr, "CLOSED", actor, now)
        return self._cr_view(cr, head)

    def history(self, playbook_id):
        head = self._head(playbook_id)
        rows = self.db.execute(
            select(PlaybookRevision, PlaybookChangeRequest)
            .outerjoin(
                PlaybookChangeRequest,
                and_(
                    PlaybookChangeRequest.playbook_id == PlaybookRevision.playbook_id,
                    PlaybookChangeRequest.revision == PlaybookRevision.revision,
                ),
            )
            .where(
                PlaybookRevision.playbook_id == playbook_id,
                PlaybookRevision.status == "PUBLISHED",
            )
            .order_by(PlaybookRevision.revision.desc())
            .execution_options(populate_existing=True)
        ).all()
        return [
            dict(
                revision=row.revision,
                digest=row.digest,
                published_at=timestamp(row.published_at),
                published_by=row.updated_by,
                base_revision=row.base_revision,
                current=row.revision == head.published_revision,
                change_request=dict(id=cr.id, title=cr.title) if cr else None,
            )
            for row, cr in rows
        ]

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

    Sequential transitions mirror SQL semantics, including change-request error
    order. Every check precedes the first mutation so a refused call leaves no
    partial state. Transaction rollback is owned by the test/service unit of work;
    this fake deliberately performs no I/O.
    """

    def __init__(self):
        self.heads = {}
        self.revisions = {}
        self.requests = {}

    def _head(self, playbook_id):
        if playbook_id not in self.heads:
            raise PlaybookNotFound("Playbook not found.")
        return self.heads[playbook_id]

    def head(self, playbook_id):
        return deepcopy(self._head(playbook_id))

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
                    "open_change_requests": sum(
                        1
                        for cr in self.requests.values()
                        if cr["playbook_id"] == playbook_id and cr["status"] == "OPEN"
                    ),
                    "revisions": [
                        {
                            key: row[key]
                            for key in (
                                "revision",
                                "status",
                                "digest",
                                "draft_version",
                                "base_revision",
                                "updated_at",
                            )
                        }
                        for row in revisions
                    ],
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

    def _published_revisions(self, playbook_id):
        return {
            rev
            for (pid, rev), row in self.revisions.items()
            if pid == playbook_id and row["status"] == "PUBLISHED"
        }

    def _cr_view(self, cr):
        head = self._head(cr["playbook_id"])
        return change_request_view(
            cr,
            self.get(cr["playbook_id"], cr["revision"]),
            head["published_revision"],
            self._published_revisions(cr["playbook_id"]),
        )

    def _cr(self, playbook_id, change_request_id):
        cr = self.requests.get(change_request_id)
        if cr is None or cr["playbook_id"] != playbook_id:
            raise ChangeRequestNotFound("Change request not found.")
        return cr

    def _open_cr_for(self, playbook_id, revision):
        cr = next(
            (
                cr
                for cr in self.requests.values()
                if cr["playbook_id"] == playbook_id and cr["revision"] == revision
            ),
            None,
        )
        if cr is None or cr["status"] != "OPEN":
            raise ChangeRequestNotOpen(
                "This draft has no open change request; it cannot be changed or published."
            )
        return cr

    def _draft(self, document, actor, now, base_revision=None):
        row = dict(
            id=document["id"],
            revision=document["revision"],
            status="DRAFT",
            digest=None,
            draft_version=1,
            base_revision=base_revision,
            document=deepcopy(document),
            created_by=actor,
            updated_by=actor,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            published_at=None,
        )
        self.revisions[row["id"], row["revision"]] = row
        return row

    def _open(self, row, origin, previous_base, title, description, actor, now):
        cr = dict(
            id=len(self.requests) + 1,
            playbook_id=row["id"],
            revision=row["revision"],
            base_revision=row["base_revision"],
            origin=origin,
            previous_base_revision=previous_base,
            title=title,
            description=description or "",
            status="OPEN",
            version=1,
            opened_by=actor,
            opened_at=now.isoformat(),
            closed_by=None,
            closed_at=None,
            published_revision=None,
        )
        self.requests[cr["id"]] = cr
        view = self.get(row["id"], row["revision"])
        view["change_request"] = self._cr_view(cr)
        return view

    @staticmethod
    def _finish(cr, status, actor, now):
        if cr["status"] != "OPEN":
            raise ChangeRequestNotOpen(
                "The change request is no longer open; refresh before continuing."
            )
        cr.update(
            status=status,
            closed_by=actor,
            closed_at=now.isoformat(),
            published_revision=cr["revision"] if status == "PUBLISHED" else None,
            version=cr["version"] + 1,
        )

    def _allocate(self, head, source_document, actor, now):
        document = deepcopy(source_document)
        document["revision"] = 1 + max(
            rev for pid, rev in self.revisions if pid == head["id"]
        )
        return self._draft(document, actor, now, head["published_revision"])

    def create(self, document, actor, now, *, title=None, description=""):
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
        row = self._draft(document, actor, now)
        return self._open(
            row,
            "CREATE",
            None,
            title or default_title("CREATE", document["id"]),
            description,
            actor,
            now,
        )

    def _generation(self, head, expected):
        if head["generation"] != expected:
            raise PlaybookConflict("The playbook changed; refresh before continuing.")
        head["generation"] += 1

    def create_draft(
        self,
        playbook_id,
        source_revision,
        expected_generation,
        actor,
        now,
        *,
        title=None,
        description="",
    ):
        head = self._head(playbook_id)
        document = self.get(playbook_id, source_revision)["document"]
        if head["published_revision"] not in (None, source_revision):
            raise PlaybookConflict(
                "New change requests start from the published revision; "
                "restore historical revisions explicitly."
            )
        self._generation(head, expected_generation)
        row = self._allocate(head, document, actor, now)
        return self._open(
            row,
            "DRAFT",
            None,
            title or default_title("DRAFT", playbook_id),
            description,
            actor,
            now,
        )

    def restore(
        self,
        playbook_id,
        source_revision,
        expected_generation,
        actor,
        now,
        *,
        title=None,
        description="",
    ):
        head = self._head(playbook_id)
        source = self.get(playbook_id, source_revision)
        if source["status"] != "PUBLISHED":
            raise PlaybookConflict("Only published revisions can be restored.")
        self._generation(head, expected_generation)
        row = self._allocate(head, source["document"], actor, now)
        return self._open(
            row,
            "RESTORE",
            source_revision,
            title or default_title("RESTORE", playbook_id, source_revision),
            description,
            actor,
            now,
        )

    def recreate_from_head(
        self,
        playbook_id,
        change_request_id,
        expected_draft_version,
        expected_generation,
        actor,
        now,
    ):
        head = self._head(playbook_id)
        old = self._cr(playbook_id, change_request_id)
        if old["status"] != "OPEN":
            raise ChangeRequestNotOpen("The change request is no longer open.")
        draft = self._editable(playbook_id, old["revision"], expected_draft_version)
        if old["base_revision"] == head["published_revision"]:
            raise NotBehindHead("The change request already targets the published revision.")
        self._generation(head, expected_generation)
        row = self._allocate(head, draft["document"], actor, now)
        view = self._open(
            row,
            "RECREATE",
            old["base_revision"],
            old["title"],
            old["description"],
            actor,
            now,
        )
        self._finish(old, "CLOSED", actor, now)
        return view

    def _editable(self, playbook_id, revision, expected):
        row = self.get(playbook_id, revision)
        if row["status"] != "DRAFT" or row["draft_version"] != expected:
            raise PlaybookConflict(
                "Draft changed or already published; refresh before continuing."
            )
        return self.revisions[playbook_id, revision]

    def edit(self, playbook_id, revision, document, expected_draft_version, actor, now):
        self.get(playbook_id, revision)
        cr = self._open_cr_for(playbook_id, revision)
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
        view = self.get(playbook_id, revision)
        view["change_request"] = self._cr_view(cr)
        return view

    def _current_base(self, cr):
        head = self.heads[cr["playbook_id"]]["published_revision"]
        if cr["base_revision"] != head:
            raise BehindHead(behind_message(cr["base_revision"], head))

    def publishable(self, playbook_id, revision):
        self.get(playbook_id, revision)
        cr = self._open_cr_for(playbook_id, revision)
        self._current_base(cr)
        return self._cr_view(cr)

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
        self.get(playbook_id, revision)
        cr = self._open_cr_for(playbook_id, revision)
        self._current_base(cr)
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
        self._finish(cr, "PUBLISHED", actor, now)
        view = self.get(playbook_id, revision)
        view["change_request"] = self._cr_view(cr)
        return view

    def change_requests(self, playbook_id, status=None):
        self._head(playbook_id)
        return [
            self._cr_view(cr)
            for cr in sorted(self.requests.values(), key=lambda c: -c["id"])
            if cr["playbook_id"] == playbook_id
            and (status is None or cr["status"] == status)
        ]

    def change_request(self, playbook_id, change_request_id):
        self._head(playbook_id)
        return self._cr_view(self._cr(playbook_id, change_request_id))

    def update_change_request(
        self,
        playbook_id,
        change_request_id,
        expected_version,
        *,
        title=None,
        description=None,
    ):
        self._head(playbook_id)
        cr = self._cr(playbook_id, change_request_id)
        if cr["status"] != "OPEN":
            raise ChangeRequestNotOpen("Only open change requests can be edited.")
        if cr["version"] != expected_version:
            raise PlaybookConflict("Change request changed; refresh before editing.")
        if title is not None:
            cr["title"] = title
        if description is not None:
            cr["description"] = description
        cr["version"] += 1
        return self._cr_view(cr)

    def close_change_request(self, playbook_id, change_request_id, actor, now):
        self._head(playbook_id)
        cr = self._cr(playbook_id, change_request_id)
        if cr["status"] != "OPEN":
            raise ChangeRequestNotOpen("Only open change requests can be closed.")
        self._finish(cr, "CLOSED", actor, now)
        return self._cr_view(cr)

    def history(self, playbook_id):
        head = self._head(playbook_id)
        titles = {
            cr["revision"]: dict(id=cr["id"], title=cr["title"])
            for cr in self.requests.values()
            if cr["playbook_id"] == playbook_id
        }
        return [
            dict(
                revision=row["revision"],
                digest=row["digest"],
                published_at=row["published_at"],
                published_by=row["updated_by"],
                base_revision=row["base_revision"],
                current=row["revision"] == head["published_revision"],
                change_request=titles.get(row["revision"]),
            )
            for row in sorted(
                (
                    r
                    for (pid, _), r in self.revisions.items()
                    if pid == playbook_id and r["status"] == "PUBLISHED"
                ),
                key=lambda r: -r["revision"],
            )
        ]

    def lock(self, playbook_id):
        return self._head(playbook_id)["generation"]

    def lock_published(self, playbook_id):
        revision = self._head(playbook_id)["published_revision"]
        if revision is None:
            raise PlaybookNotFound("No published playbook revision.")
        row = self.get(playbook_id, revision)
        return revision, row["digest"]
