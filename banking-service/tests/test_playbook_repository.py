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

"""Storage conformance, administration, immutable pins, and concurrency."""

from copy import deepcopy
import datetime
import json
import os
import threading
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from models.audit import AuditOutbox
from models.playbook import Playbook, PlaybookRevision
from services.playbook_repository import (
    MemoryPlaybookRepository,
    SqlPlaybookRepository,
    PlaybookConflict,
    PlaybookNotFound,
    RepositoryError,
)
from services.playbook_administration import PlaybookAdministration
from services.proposal_definitions import (
    bundled_documents,
    definition_digest,
    load_action_registry,
)
from services.playbook_discovery import discover_playbooks

NOW = datetime.datetime(2026, 10, 4, tzinfo=datetime.timezone.utc)
PG_URL = os.environ.get("PLAYBOOK_TEST_DATABASE_URL")


def document():
    d = next(
        d
        for d in bundled_documents()
        if d["id"] == "card-reissue" and d["schema_version"] == 2
    )
    suffix = uuid.uuid4().hex
    return dict(d, id="test-" + suffix, action_type="TEST_" + suffix, revision=1)


@pytest.fixture(params=["memory", "sqlite", "postgresql"])
def repository(request, tmp_path):
    if request.param == "memory":
        yield MemoryPlaybookRepository()
        return
    if request.param == "postgresql" and not PG_URL:
        pytest.skip(
            "PLAYBOOK_TEST_DATABASE_URL selects an isolated migrated PostgreSQL database"
        )
    engine = create_engine(
        PG_URL
        if request.param == "postgresql"
        else f"sqlite:///{tmp_path / 'catalog.db'}"
    )
    if request.param == "sqlite":
        for model in (Playbook, PlaybookRevision, AuditOutbox):
            model.__table__.create(engine, checkfirst=True)
    with Session(engine) as db:
        try:
            yield SqlPlaybookRepository(db)
        finally:
            db.rollback()
    engine.dispose()


def test_repository_conformance_publication_history_and_conflicts(repository):
    d = document()
    draft = repository.create(d, "alice", NOW)
    assert not any(x[0] == d["id"] for x in repository.snapshot().published)
    published = repository.publish(
        d["id"], 1, definition_digest(d), 1, draft["generation"], "alice", NOW
    )
    assert repository.lock_published(d["id"]) == (1, definition_digest(d))
    with pytest.raises(PlaybookConflict):
        repository.edit(d["id"], 1, d, 1, "alice", NOW)
    second = repository.create_draft(d["id"], 1, published["generation"], "bob", NOW)
    with pytest.raises(PlaybookConflict):
        repository.create_draft(d["id"], 1, published["generation"], "bob", NOW)
    changed = deepcopy(second["document"])
    changed["discovery"]["purpose"] = "Updated operator guidance"
    edited = repository.edit(d["id"], 2, changed, 1, "bob", NOW)
    with pytest.raises(PlaybookConflict):
        repository.edit(d["id"], 2, changed, 1, "bob", NOW)
    with pytest.raises(PlaybookConflict):
        repository.publish(
            d["id"], 2, definition_digest(changed), 1, second["generation"], "bob", NOW
        )
    repository.publish(
        d["id"],
        2,
        definition_digest(changed),
        edited["draft_version"],
        second["generation"],
        "bob",
        NOW,
    )
    snapshot = repository.snapshot()
    assert (d["id"], 2) in snapshot.published and (d["id"], 1) not in snapshot.published
    assert repository.get(d["id"], 1)["digest"] == definition_digest(d)
    found = next(doc for doc in snapshot.documents if doc["id"] == d["id"])
    found["discovery"]["purpose"] = "Mutated return value"
    assert repository.get(d["id"], 1)["document"] == d
    with pytest.raises(PlaybookNotFound):
        repository.get("missing", 1)


def test_repository_refuses_capability_rebinding(repository):
    d = document()
    repository.create(d, "operator", NOW)
    changed = dict(d, operation="credit.adjust_limit.v1")
    with pytest.raises(RepositoryError, match="immutable"):
        repository.edit(d["id"], 1, changed, 1, "operator", NOW)


@pytest.fixture
def administration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'administration.db'}")
    for model in (Playbook, PlaybookRevision, AuditOutbox):
        model.__table__.create(engine, checkfirst=True)
    with Session(engine) as db:
        yield PlaybookAdministration(db, clock=lambda: NOW)
    engine.dispose()


def test_admin_config_only_addition_validation_diff_publish_and_history(administration):
    service = administration
    d = document()
    first = service.create(d, "alice")
    assert service.validate(d["id"], 1, 1)["valid"]
    before = discover_playbooks(load_action_registry(service.db), "Damaged card")
    assert d["id"] not in {p["playbook_id"] for p in before["playbooks"]}
    published = service.publish(d["id"], 1, 1, first["generation"], "alice")
    registry = load_action_registry(service.db)
    assert registry.published(d["id"]).definition_digest == definition_digest(d)
    draft = service.create_draft(d["id"], 1, published["generation"], "bob")
    changed = deepcopy(draft["document"])
    changed["discovery"]["purpose"] = "Updated guidance"
    saved = service.edit(d["id"], draft["revision"], changed, 1, "bob")
    assert {c["path"] for c in service.compare(d["id"], 1, 2)["changes"]} == {
        "/revision",
        "/discovery/purpose",
    }
    service.publish(d["id"], 2, saved["draft_version"], draft["generation"], "bob")
    refreshed = load_action_registry(service.db)
    assert refreshed.published(d["id"]).definition_revision == 2
    assert refreshed.resolve(d["id"], 1, definition_digest(d)).definition_revision == 1
    with pytest.raises(ValueError):
        refreshed.resolve(d["id"], 1, "0" * 64)
    events = [
        json.loads(row.payload)
        for row in service.db.query(AuditOutbox).filter_by(
            event_type="PLAYBOOK_PUBLISHED"
        )
    ]
    assert events[-1]["previous_published"] == {
        "revision": 1,
        "digest": definition_digest(d),
    }
    assert all("document" not in event for event in events)
    assert (
        service.db.query(AuditOutbox)
        .filter_by(event_type="PROPOSAL_EVIDENCE_SNAPSHOT")
        .count()
        == 2
    )
    evidence = json.loads(
        service.db.query(AuditOutbox)
        .filter_by(event_type="PROPOSAL_EVIDENCE_SNAPSHOT")
        .first()
        .payload
    )
    assert json.loads(evidence["snapshot_json"])["definition"] == d


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(authorization_policy="none"),
        lambda d: d["presentation"].update(public_payload_fields=["card_token"]),
        lambda d: d["presentation"].update(template="{card_last_four.__class__}"),
        lambda d: d["discovery"].update(purpose=""),
        lambda d: d.update(schema_version=1),
    ],
)
def test_invalid_draft_cannot_publish(administration, mutation):
    d = document()
    mutation(d)
    draft = administration.create(d, "operator")
    assert not administration.validate(d["id"], 1, 1)["valid"]
    with pytest.raises(RepositoryError):
        administration.publish(d["id"], 1, 1, draft["generation"], "operator")
    assert administration.get(d["id"], 1)["status"] == "DRAFT"
    assert (
        administration.db.query(AuditOutbox)
        .filter_by(event_type="PLAYBOOK_PUBLISHED")
        .count()
        == 0
    )


@pytest.mark.parametrize(
    "field", ["id", "revision", "action_type", "contract_version", "operation"]
)
def test_edit_cannot_rebind_identity_or_capability(administration, field):
    d = document()
    administration.create(d, "alice")
    changed = dict(d, **{field: 2 if field == "revision" else "changed"})
    with pytest.raises(RepositoryError):
        administration.edit(d["id"], 1, changed, 1, "alice")


def test_document_size_depth_and_unknown_dto_fields_refused(administration):
    d = document()
    d["unbounded"] = "x" * 65537
    with pytest.raises(RepositoryError, match="64 KiB"):
        administration.create(d, "operator")
    d = document()
    nested = {}
    d["nested"] = nested
    for _ in range(18):
        nested["child"] = {}
        nested = nested["child"]
    with pytest.raises(RepositoryError, match="nesting"):
        administration.create(d, "operator")


def test_management_audit_failure_rolls_back_publication(administration, monkeypatch):
    d = document()
    draft = administration.create(d, "operator")

    def fail(*args, **kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr("services.playbook_administration.record_audit_event", fail)
    with pytest.raises(RuntimeError):
        administration.publish(d["id"], 1, 1, draft["generation"], "operator")
    assert administration.get(d["id"], 1)["status"] == "DRAFT"
    assert administration.repository._head(d["id"]).published_revision is None
    assert (
        administration.db.query(AuditOutbox)
        .filter_by(event_type="PROPOSAL_EVIDENCE_SNAPSHOT")
        .count()
        == 0
    )


def test_admin_routes_require_admin_for_every_operation(administration, monkeypatch):
    from main import app
    from routers.playbooks_admin import get_administration
    from utils.auth import get_current_user
    from models.authentication import ValidatedToken

    monkeypatch.setattr("utils.auth.is_running_locally", lambda: False)
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(
        claims={"sub": "customer", "email": "customer@example.com"}
    )
    app.dependency_overrides[get_administration] = lambda: administration
    try:
        with TestClient(app) as client:
            for method, path, body in [
                ("GET", "", None),
                ("GET", "/capabilities", None),
                ("POST", "", {"document": document()}),
                ("GET", "/x/revisions/1", None),
                ("POST", "/x/drafts", {"source_revision": 1, "expected_generation": 1}),
                (
                    "PUT",
                    "/x/drafts/1",
                    {"document": document(), "expected_draft_version": 1},
                ),
                ("POST", "/x/drafts/1/validate", {"expected_draft_version": 1}),
                (
                    "POST",
                    "/x/drafts/1/publish",
                    {"expected_draft_version": 1, "expected_generation": 1},
                ),
                ("GET", "/x/compare?from_revision=1&to_revision=2", None),
            ]:
                response = client.request(method, "/admin/playbooks" + path, json=body)
                assert response.status_code == 403, (path, response.text)
    finally:
        app.dependency_overrides.pop(get_administration, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("action", ["UPDATE", "DELETE"])
def test_sql_database_rejects_published_mutation(administration, action):
    d = document()
    draft = administration.create(d, "operator")
    administration.publish(d["id"], 1, 1, draft["generation"], "operator")
    statement = (
        "UPDATE admin.playbook_revisions SET digest='changed'"
        if action == "UPDATE"
        else "DELETE FROM admin.playbook_revisions"
    )
    with pytest.raises(DBAPIError):
        administration.db.execute(
            text(statement + " WHERE playbook_id=:id AND revision=1"), {"id": d["id"]}
        )
    administration.db.rollback()
    assert administration.get(d["id"], 1)["digest"] == definition_digest(d)


@pytest.mark.skipif(not PG_URL, reason="isolated PostgreSQL URL required")
def test_postgres_publication_race_has_one_winner_and_restart_preserves_pin():
    engine = create_engine(PG_URL)
    d = document()
    with Session(engine) as db:
        service = PlaybookAdministration(db, clock=lambda: NOW)
        initial = service.create(d, "operator")
    barrier = threading.Barrier(2)
    outcomes = []

    def publish():
        with Session(engine) as db:
            service = PlaybookAdministration(db, clock=lambda: NOW)
            barrier.wait(timeout=5)
            try:
                service.publish(d["id"], 1, 1, initial["generation"], "operator")
                outcomes.append("published")
            except PlaybookConflict:
                outcomes.append("conflict")

    threads = [threading.Thread(target=publish) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(outcomes) == ["conflict", "published"]
    with Session(engine) as db:
        assert (
            load_action_registry(db)
            .resolve(d["id"], 1, definition_digest(d))
            .definition_revision
            == 1
        )
        with pytest.raises(DBAPIError):
            db.execute(
                text(
                    "UPDATE admin.playbook_revisions SET digest='tampered' WHERE playbook_id=:id"
                ),
                {"id": d["id"]},
            )
        db.rollback()
    engine.dispose()


def test_admin_http_workflow_and_conflict_envelopes(administration, monkeypatch):
    from main import app
    from routers.playbooks_admin import get_administration
    from utils.auth import get_current_user
    from models.authentication import ValidatedToken

    monkeypatch.setattr("utils.auth.is_running_locally", lambda: False)
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(
        claims={"sub": "operator", "email": "operator@gcp.solutions"}
    )
    app.dependency_overrides[get_administration] = lambda: administration
    try:
        with TestClient(app) as client:
            templates = client.get("/admin/playbooks/capabilities").json()["operations"]
            assert {op["operation"] for op in templates} == {
                d["operation"] for d in bundled_documents()
            }
            d = document()
            response = client.post("/admin/playbooks", json={"document": d})
            assert response.status_code == 201, response.text
            draft = response.json()
            assert (
                client.get(f"/admin/playbooks/{d['id']}/revisions/1").json()["document"]
                == d
            )
            assert client.post(
                f"/admin/playbooks/{d['id']}/drafts/1/validate",
                json={"expected_draft_version": 1},
            ).json()["valid"]
            wrong = client.post(
                f"/admin/playbooks/{d['id']}/drafts/1/publish",
                json={"expected_draft_version": 1, "expected_generation": 0},
            )
            assert (
                wrong.status_code == 409
                and wrong.json()["detail"]["code"] == "PLAYBOOK_CONFLICT"
            )
            success = client.post(
                f"/admin/playbooks/{d['id']}/drafts/1/publish",
                json={
                    "expected_draft_version": 1,
                    "expected_generation": draft["generation"],
                },
            )
            assert (
                success.status_code == 200 and success.json()["status"] == "PUBLISHED"
            )
            assert (
                client.post(
                    "/admin/playbooks", json={"document": d, "unexpected": True}
                ).status_code
                == 422
            )
            assert client.get("/admin/playbooks/missing/revisions/1").status_code == 404
    finally:
        app.dependency_overrides.pop(get_administration, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.skipif(not PG_URL, reason="isolated PostgreSQL URL required")
@pytest.mark.parametrize("transition", ["edit", "allocate"])
def test_postgres_concurrent_draft_writes_reject_stale_versions(transition):
    engine = create_engine(PG_URL)
    d = document()
    with Session(engine) as db:
        initial = PlaybookAdministration(db, clock=lambda: NOW).create(d, "operator")
    barrier = threading.Barrier(2)
    outcomes = []

    def change():
        with Session(engine) as db:
            service = PlaybookAdministration(db, clock=lambda: NOW)
            barrier.wait(timeout=5)
            try:
                if transition == "edit":
                    service.edit(d["id"], 1, d, 1, "operator")
                else:
                    service.create_draft(d["id"], 1, initial["generation"], "operator")
                outcomes.append("success")
            except PlaybookConflict:
                outcomes.append("conflict")

    threads = [threading.Thread(target=change) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(outcomes) == ["conflict", "success"]
    engine.dispose()


@pytest.mark.skipif(not PG_URL, reason="isolated PostgreSQL URL required")
def test_postgres_stale_service_cannot_prepare_replaced_publication():
    from services.action_proposals import ActionProposalService, ProposalError
    from services.action_proposal_context import ProposalRuntimeContext
    from models.identity import User

    engine = create_engine(PG_URL)
    d = document()
    with Session(engine) as db:
        admin = PlaybookAdministration(db, clock=lambda: NOW)
        draft = admin.create(d, "operator")
        admin.publish(d["id"], 1, 1, draft["generation"], "operator")
        user = User(
            id=uuid.uuid4(),
            auth_provider_uid="pin-" + uuid.uuid4().hex,
            email=uuid.uuid4().hex + "@example.com",
        )
        db.add(user)
        db.commit()
        identity = user.auth_provider_uid
        stale = ActionProposalService(db)
        pin = stale.registry.published(d["id"])
        with Session(engine) as publishing_db:
            publishing_admin = PlaybookAdministration(publishing_db, clock=lambda: NOW)
            next_draft = publishing_admin.create_draft(d["id"], 1, 2, "operator")
            publishing_admin.publish(
                d["id"], 2, 1, next_draft["generation"], "operator"
            )
        context = ProposalRuntimeContext(
            support_session_id="pin-scope",
            runtime_name="ADK_GEMINI_LIVE",
            runtime_session_id="pin-runtime",
            customer_turn_id="turn1",
            reset_generation="generation1",
        )
        with pytest.raises(ProposalError, match="published playbook changed"):
            stale.prepare_playbook_for_identity(
                playbook_id=d["id"],
                revision=1,
                digest=pin.definition_digest,
                inputs={"reason": "LOST"},
                customer_identity=identity,
                runtime_context=context,
                idempotency_key="stale",
            )
    engine.dispose()


@pytest.mark.skipif(not PG_URL, reason="isolated PostgreSQL URL required")
def test_postgres_publish_waits_for_head_lock():
    import time

    engine = create_engine(PG_URL)
    d = document()
    with Session(engine) as db:
        initial = PlaybookAdministration(db, clock=lambda: NOW).create(d, "operator")
    errors = []
    started = threading.Event()
    with Session(engine) as preparation_db:
        SqlPlaybookRepository(preparation_db).lock(d["id"])

        def publish():
            with Session(engine) as db:
                try:
                    db.execute(
                        text("SET application_name='playbook-publish-lock-test'")
                    )
                    started.set()
                    PlaybookAdministration(db, clock=lambda: NOW).publish(
                        d["id"], 1, 1, initial["generation"], "operator"
                    )
                except Exception as exc:
                    errors.append(exc)

        thread = threading.Thread(target=publish)
        thread.start()
        assert started.wait(5)
        deadline = time.monotonic() + 5
        blocked = False
        while time.monotonic() < deadline:
            with engine.connect() as connection:
                blocked = bool(
                    connection.execute(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE application_name='playbook-publish-lock-test' AND wait_event_type='Lock'"
                        )
                    ).scalar()
                )
            if blocked:
                break
            time.sleep(0.01)
        assert blocked, (
            "Publication did not serialize on the active preparation head lock"
        )
        assert thread.is_alive()
        preparation_db.commit()
        thread.join(timeout=10)
        assert not thread.is_alive() and not errors
    engine.dispose()


@pytest.mark.skipif(not PG_URL, reason="isolated PostgreSQL URL required")
def test_postgres_concurrent_explicit_bootstrap_is_atomic_and_idempotent():
    from services.playbook_repository import bootstrap_catalog

    schema = "playbook_bootstrap_" + uuid.uuid4().hex
    base_engine = create_engine(PG_URL)
    with base_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = base_engine.execution_options(schema_translate_map={"admin": schema})
    try:
        Playbook.__table__.create(engine)
        PlaybookRevision.__table__.create(engine)
        barrier = threading.Barrier(2)
        errors = []

        def initialize():
            try:
                with Session(engine) as db:
                    barrier.wait(timeout=5)
                    bootstrap_catalog(db, bundled_documents(), now=NOW)
                    db.commit()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=initialize) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert not errors and all(not thread.is_alive() for thread in threads)
        with Session(engine) as db:
            snapshot = SqlPlaybookRepository(db).snapshot()
            assert len(snapshot.documents) == 7 and len(snapshot.published) == 4
            registry = load_action_registry(db)
            for d in bundled_documents():
                assert registry.resolve(d["id"], d["revision"], definition_digest(d))
            head = db.get(Playbook, "card-reissue")
            head.generation = 99
            db.commit()
            bootstrap_catalog(db, bundled_documents(), now=NOW)
            db.commit()
            assert db.get(Playbook, "card-reissue").generation == 99
    finally:
        with base_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base_engine.dispose()


def test_fresh_local_startup_synchronously_bootstraps_catalog(tmp_path):
    import subprocess
    import sys

    env = dict(
        os.environ,
        DATABASE_URL=f"sqlite:///{tmp_path / 'fresh.db'}",
        DISABLE_INIT_DB="false",
        ENABLE_STARTUP_DB_SEEDING="false",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            'from main import app\nfrom utils.database import SessionLocal\nfrom services.proposal_definitions import load_action_registry\nfrom services.playbook_repository import SqlPlaybookRepository\nwith SessionLocal() as db:\n r=load_action_registry(db)\n assert len(r.action_types)==4\n assert len(SqlPlaybookRepository(db).snapshot().documents)==7\n print("fresh-startup-four-published-seven-history")',
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "fresh-startup-four-published-seven-history" in result.stdout


@pytest.mark.parametrize("operation", [None, "os.system", {}, "x" * 129])
def test_unregistered_execution_reference_refused_at_creation(
    administration, operation
):
    d = document()
    d["operation"] = operation
    with pytest.raises(RepositoryError):
        administration.create(d, "operator")
    assert not any(row["id"] == d["id"] for row in administration.list()["playbooks"])


def test_repository_migration_freezes_history_and_preserves_other_admin_data(tmp_path):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    path = (
        Path(__file__).parents[1]
        / "alembic/versions/b92e3d8a601c_versioned_playbook_repository.py"
    )
    spec = importlib.util.spec_from_file_location("playbook_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "a81d2c7f490b"
    assert migration.BOOTSTRAP == bundled_documents()
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE admin.existing_settings (value TEXT)"))
        connection.execute(
            text("INSERT INTO admin.existing_settings VALUES ('preserved')")
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert (
            connection.execute(
                text("SELECT count(*) FROM admin.playbook_revisions")
            ).scalar()
            == 7
        )
        assert (
            connection.execute(text("SELECT count(*) FROM admin.playbooks")).scalar()
            == 4
        )
        migration.downgrade()
        assert (
            connection.execute(
                text("SELECT value FROM admin.existing_settings")
            ).scalar()
            == "preserved"
        )
        migration.upgrade()
        with Session(bind=connection) as db:
            snapshot = SqlPlaybookRepository(db).snapshot()
            registry = load_action_registry(db)
            assert len(snapshot.documents) == 7
            for d in migration.BOOTSTRAP:
                assert registry.resolve(d["id"], d["revision"], definition_digest(d))
    engine.dispose()


def test_compare_distinguishes_missing_fields_from_explicit_null(administration):
    d = document()
    initial = administration.create(d, "operator")
    draft = administration.create_draft(d["id"], 1, initial["generation"], "operator")
    modified = dict(draft["document"], optional_note=None)
    administration.edit(d["id"], 2, modified, 1, "operator")
    forward = administration.compare(d["id"], 1, 2)["changes"]
    backward = administration.compare(d["id"], 2, 1)["changes"]
    assert next(c for c in forward if c["path"] == "/optional_note") == {
        "path": "/optional_note",
        "before": None,
        "after": None,
        "change_type": "ADDED",
    }
    assert (
        next(c for c in backward if c["path"] == "/optional_note")["change_type"]
        == "REMOVED"
    )


@pytest.mark.parametrize("target", ["missing", "draft"])
def test_invalid_published_head_refuses_entire_catalog(administration, target):
    d = document()
    administration.create(d, "operator")
    head = administration.db.get(Playbook, d["id"])
    head.published_revision = 999 if target == "missing" else 1
    administration.db.commit()
    with pytest.raises(RepositoryError, match="head.*invalid"):
        load_action_registry(administration.db)
    # The four valid bundled playbooks must not mask the corrupt operational head.
    assert administration.db.query(Playbook).count() == 5
