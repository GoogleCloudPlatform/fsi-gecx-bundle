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

"""Persisted operational playbooks; published revisions are immutable."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    JSON,
    String,
    ForeignKeyConstraint,
    event,
    DDL,
)
from utils.database import Base


class Playbook(Base):
    __tablename__ = "playbooks"
    __table_args__ = ({"schema": "admin"},)
    id = Column(String(128), primary_key=True)
    action_type = Column(String(64), unique=True, nullable=False)
    contract_version = Column(String(32), nullable=False)
    operation = Column(String(128), nullable=False)
    published_revision = Column(Integer, nullable=True)
    generation = Column(Integer, nullable=False, default=0)


class PlaybookRevision(Base):
    __tablename__ = "playbook_revisions"
    __table_args__ = (
        ForeignKeyConstraint(["playbook_id"], ["admin.playbooks.id"]),
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED')", name="ck_playbook_revision_status"
        ),
        CheckConstraint(
            "revision > 0 AND draft_version > 0", name="ck_playbook_revision_versions"
        ),
        CheckConstraint(
            "status != 'PUBLISHED' OR (digest IS NOT NULL AND published_at IS NOT NULL)",
            name="ck_playbook_published_identity",
        ),
        {"schema": "admin"},
    )
    playbook_id = Column(String(128), primary_key=True)
    revision = Column(Integer, primary_key=True)
    status = Column(String(16), nullable=False)
    document = Column(JSON, nullable=False)
    digest = Column(String(64), nullable=True)
    draft_version = Column(Integer, nullable=False, default=1)
    created_by = Column(String(255), nullable=False)
    updated_by = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)


# Local SQLite metadata initialization enforces immutability. PostgreSQL uses
# the migration-installed trigger and must be migrated before accepting traffic.
event.listen(
    PlaybookRevision.__table__,
    "after_create",
    DDL("""
CREATE TRIGGER admin.playbook_revision_immutable_update
BEFORE UPDATE ON playbook_revisions WHEN OLD.status = 'PUBLISHED'
BEGIN SELECT RAISE(ABORT, 'Published playbook revisions are immutable'); END
""").execute_if(dialect="sqlite"),
)
event.listen(
    PlaybookRevision.__table__,
    "after_create",
    DDL("""
CREATE TRIGGER admin.playbook_revision_immutable_delete
BEFORE DELETE ON playbook_revisions WHEN OLD.status = 'PUBLISHED'
BEGIN SELECT RAISE(ABORT, 'Published playbook revisions are immutable'); END
""").execute_if(dialect="sqlite"),
)


@event.listens_for(PlaybookRevision.__table__, "after_create")
def initialize_local_catalog(target, connection, **kwargs):
    """SQLite create_all is the explicit local init path; deployed SQL uses migration."""
    if connection.dialect.name != "sqlite":
        return
    import datetime
    import hashlib
    import json
    from pathlib import Path

    now = datetime.datetime.now(datetime.timezone.utc)
    documents = [
        json.loads(path.read_text())
        for path in sorted(
            (Path(__file__).resolve().parents[1] / "config/action_definitions").glob(
                "*.json"
            )
        )
    ]
    groups = {}
    for document in documents:
        groups.setdefault(document["id"], []).append(document)
    for playbook_id, versions in groups.items():
        latest = max(versions, key=lambda d: d["revision"])
        connection.execute(
            Playbook.__table__.insert().values(
                id=playbook_id,
                action_type=latest["action_type"],
                contract_version=latest["contract_version"],
                operation=latest["operation"],
                published_revision=latest["revision"],
                generation=1,
            )
        )
        for document in versions:
            digest = hashlib.sha256(
                json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            connection.execute(
                target.insert().values(
                    playbook_id=playbook_id,
                    revision=document["revision"],
                    status="PUBLISHED",
                    document=document,
                    digest=digest,
                    draft_version=1,
                    created_by="bundle-bootstrap",
                    updated_by="bundle-bootstrap",
                    created_at=now,
                    updated_at=now,
                    published_at=now,
                )
            )
