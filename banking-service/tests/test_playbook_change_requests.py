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

"""Change-request lifecycle, behind detection, restore, policy and HTTP contract."""

from copy import deepcopy
import datetime
import json
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from models.audit import AuditOutbox
from models.playbook import Playbook, PlaybookRevision, PlaybookChangeRequest
from services.playbook_administration import PlaybookAdministration
from services.playbook_policy import PublishPolicy
from services.playbook_repository import (
    BehindHead,
    ChangeRequestNotFound,
    ChangeRequestNotOpen,
    MemoryPlaybookRepository,
    NotBehindHead,
    PlaybookConflict,
    RepositoryError,
    SqlPlaybookRepository,
)
from services.proposal_definitions import bundled_documents, definition_digest

NOW = datetime.datetime(2026, 10, 6, tzinfo=datetime.timezone.utc)
PG_URL = os.environ.get("PLAYBOOK_TEST_DATABASE_URL")
TABLES = (Playbook, PlaybookRevision, PlaybookChangeRequest, AuditOutbox)


def document():
    d = next(
        d
        for d in bundled_documents()
        if d["id"] == "card-reissue" and d["schema_version"] == 2
    )
    suffix = uuid.uuid4().hex
    return dict(deepcopy(d), id="cr-" + suffix, action_type="CR_" + suffix, revision=1)


def purpose(draft, value):
    changed = deepcopy(draft["document"])
    changed["discovery"]["purpose"] = value
    return changed


@pytest.fixture(params=["memory", "sqlite", "postgresql"])
def repository(request, tmp_path):
    if request.param == "memory":
        yield MemoryPlaybookRepository()
        return
    if request.param == "postgresql" and not PG_URL:
        pytest.skip("PLAYBOOK_TEST_DATABASE_URL selects an isolated migrated PostgreSQL database")
    engine = create_engine(
        PG_URL if request.param == "postgresql" else f"sqlite:///{tmp_path / 'cr.db'}"
    )
    if request.param == "sqlite":
        for model in TABLES:
            model.__table__.create(engine, checkfirst=True)
    with Session(engine) as db:
        try:
            yield SqlPlaybookRepository(db)
        finally:
            db.rollback()
    engine.dispose()


def published_playbook(repository, actor="alice"):
    d = document()
    draft = repository.create(d, actor, NOW)
    published = repository.publish(
        d["id"], 1, definition_digest(d), 1, draft["generation"], actor, NOW
    )
    return d, published


def test_drafts_open_one_change_request_based_on_current_head(repository):
    d = document()
    created = repository.create(d, "alice", NOW, title="Launch")
    assert created["change_request"] | {} == created["change_request"]
    assert {
        k: created["change_request"][k]
        for k in ("revision", "base_revision", "status", "origin", "title", "opened_by")
    } == dict(
        revision=1,
        base_revision=None,
        status="OPEN",
        origin="CREATE",
        title="Launch",
        opened_by="alice",
    )
    published = repository.publish(
        d["id"], 1, definition_digest(d), 1, created["generation"], "alice", NOW
    )
    assert published["change_request"]["status"] == "PUBLISHED"
    assert published["change_request"]["published_revision"] == 1
    draft = repository.create_draft(d["id"], 1, published["generation"], "bob", NOW)
    assert draft["base_revision"] == 1
    assert draft["change_request"]["base_revision"] == 1
    assert draft["change_request"]["title"] == f"Update {d['id']}"
    entry = next(p for p in repository.list() if p["id"] == d["id"])
    assert entry["open_change_requests"] == 1
    assert [cr["revision"] for cr in repository.change_requests(d["id"])] == [2, 1]
    assert [cr["revision"] for cr in repository.change_requests(d["id"], "OPEN")] == [2]


def test_new_drafts_start_from_the_published_head(repository):
    d, published = published_playbook(repository)
    draft = repository.create_draft(d["id"], 1, published["generation"], "bob", NOW)
    edited = repository.edit(d["id"], 2, purpose(draft, "v2"), 1, "bob", NOW)
    repository.publish(
        d["id"], 2, definition_digest(edited["document"]), 2, draft["generation"], "bob", NOW
    )
    with pytest.raises(PlaybookConflict, match="restore"):
        repository.create_draft(d["id"], 1, draft["generation"] + 1, "bob", NOW)


def test_publishing_one_change_request_puts_the_others_behind(repository):
    d, published = published_playbook(repository)
    a = repository.create_draft(d["id"], 1, published["generation"], "alice", NOW)
    b = repository.create_draft(d["id"], 1, a["generation"], "bob", NOW)
    repository.publish(
        d["id"], a["revision"], "a" * 64, 1, b["generation"], "alice", NOW
    )
    behind = repository.change_request(d["id"], b["change_request"]["id"])
    assert (behind["behind"], behind["behind_by"]) == (True, 1)
    with pytest.raises(BehindHead):
        repository.publishable(d["id"], b["revision"])
    head = repository.head(d["id"])
    with pytest.raises(BehindHead):
        repository.publish(
            d["id"], b["revision"], "b" * 64, 1, head["generation"], "bob", NOW
        )
    assert repository.head(d["id"])["published_revision"] == a["revision"]
    assert repository.get(d["id"], b["revision"])["status"] == "DRAFT"
    assert repository.change_request(d["id"], b["change_request"]["id"])["status"] == "OPEN"


def test_recreate_from_head_copies_draft_onto_head_and_closes_original(repository):
    d, published = published_playbook(repository)
    a = repository.create_draft(d["id"], 1, published["generation"], "alice", NOW)
    b = repository.create_draft(d["id"], 1, a["generation"], "bob", NOW, title="Bob")
    edited = repository.edit(d["id"], b["revision"], purpose(b, "bob text"), 1, "bob", NOW)
    repository.publish(d["id"], a["revision"], "a" * 64, 1, b["generation"], "alice", NOW)
    head = repository.head(d["id"])
    with pytest.raises(PlaybookConflict):
        repository.recreate_from_head(
            d["id"], b["change_request"]["id"], 1, head["generation"], "bob", NOW
        )
    recreated = repository.recreate_from_head(
        d["id"],
        b["change_request"]["id"],
        edited["draft_version"],
        head["generation"],
        "bob",
        NOW,
    )
    assert recreated["document"]["discovery"]["purpose"] == "bob text"
    assert recreated["base_revision"] == a["revision"]
    cr = recreated["change_request"]
    assert (cr["origin"], cr["previous_base_revision"], cr["title"], cr["behind"]) == (
        "RECREATE",
        1,
        "Bob",
        False,
    )
    assert repository.change_request(d["id"], b["change_request"]["id"])["status"] == "CLOSED"
    with pytest.raises(NotBehindHead):
        repository.recreate_from_head(
            d["id"], cr["id"], 1, repository.head(d["id"])["generation"], "bob", NOW
        )


def test_restore_creates_draft_from_history_based_on_current_head(repository):
    d, published = published_playbook(repository)
    draft = repository.create_draft(d["id"], 1, published["generation"], "bob", NOW)
    edited = repository.edit(d["id"], 2, purpose(draft, "v2"), 1, "bob", NOW)
    repository.publish(d["id"], 2, "c" * 64, 2, draft["generation"], "bob", NOW)
    generation = repository.head(d["id"])["generation"]
    open_draft = repository.create_draft(d["id"], 2, generation, "bob", NOW)
    with pytest.raises(PlaybookConflict, match="published"):
        repository.restore(d["id"], open_draft["revision"], open_draft["generation"], "bob", NOW)
    restored = repository.restore(d["id"], 1, open_draft["generation"], "carol", NOW)
    assert restored["document"] == dict(d, revision=restored["revision"])
    assert edited["document"]["discovery"]["purpose"] == "v2"
    assert restored["base_revision"] == 2
    cr = restored["change_request"]
    assert (cr["origin"], cr["previous_base_revision"], cr["title"]) == (
        "RESTORE",
        1,
        "Restore revision 1",
    )
    history = repository.history(d["id"])
    assert [(h["revision"], h["current"]) for h in history] == [(2, True), (1, False)]
    assert history[0]["change_request"]["id"] == draft["change_request"]["id"]


def test_closed_and_published_change_requests_are_final(repository):
    d, published = published_playbook(repository)
    draft = repository.create_draft(d["id"], 1, published["generation"], "bob", NOW)
    cr_id = draft["change_request"]["id"]
    closed = repository.close_change_request(d["id"], cr_id, "bob", NOW)
    assert (closed["status"], closed["closed_by"]) == ("CLOSED", "bob")
    for attempt in (
        lambda: repository.edit(d["id"], 2, draft["document"], 1, "bob", NOW),
        lambda: repository.publish(d["id"], 2, "d" * 64, 1, draft["generation"], "bob", NOW),
        lambda: repository.update_change_request(d["id"], cr_id, closed["version"], title="x"),
        lambda: repository.close_change_request(d["id"], cr_id, "bob", NOW),
        lambda: repository.close_change_request(
            d["id"], published["change_request"]["id"], "bob", NOW
        ),
    ):
        with pytest.raises(ChangeRequestNotOpen):
            attempt()
    assert repository.get(d["id"], 2)["status"] == "DRAFT"
    other, _ = published_playbook(repository)
    with pytest.raises(ChangeRequestNotFound):
        repository.change_request(other["id"], cr_id)


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_stale_reads_cannot_finish_a_change_request_closed_elsewhere(backend, tmp_path):
    if backend == "postgresql" and not PG_URL:
        pytest.skip("PLAYBOOK_TEST_DATABASE_URL selects an isolated migrated PostgreSQL database")
    engine = create_engine(
        PG_URL if backend == "postgresql" else f"sqlite:///{tmp_path / 'cas.db'}"
    )
    if backend == "sqlite":
        for model in TABLES:
            model.__table__.create(engine, checkfirst=True)
    d = document()
    try:
        with Session(engine) as setup:
            created = SqlPlaybookRepository(setup).create(d, "alice", NOW)
            setup.commit()
        cr_id = created["change_request"]["id"]
        with Session(engine) as stale, Session(engine) as other:
            stale_repository = SqlPlaybookRepository(stale)
            row = stale_repository._cr_row(d["id"], cr_id)
            assert row.status == "OPEN"
            SqlPlaybookRepository(other).close_change_request(d["id"], cr_id, "bob", NOW)
            other.commit()
            # The in-session row still says OPEN; only the status CAS protects finality.
            with pytest.raises(ChangeRequestNotOpen):
                stale_repository._finish(row, "PUBLISHED", "alice", NOW)
            stale.rollback()
        with Session(engine) as check:
            final = SqlPlaybookRepository(check).change_request(d["id"], cr_id)
            assert (final["status"], final["closed_by"]) == ("CLOSED", "bob")
    finally:
        engine.dispose()


def test_change_request_metadata_rejects_stale_versions(repository):
    d = document()
    created = repository.create(d, "alice", NOW)
    cr = created["change_request"]
    updated = repository.update_change_request(
        d["id"], cr["id"], cr["version"], title="New title", description="Why"
    )
    assert (updated["title"], updated["description"], updated["version"]) == (
        "New title",
        "Why",
        2,
    )
    with pytest.raises(PlaybookConflict):
        repository.update_change_request(d["id"], cr["id"], cr["version"], title="Lost")
    assert repository.change_request(d["id"], cr["id"])["title"] == "New title"


@pytest.fixture
def administration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'administration.db'}")
    for model in TABLES:
        model.__table__.create(engine, checkfirst=True)
    with Session(engine) as db:
        yield PlaybookAdministration(
            db, clock=lambda: NOW, policy=PublishPolicy.from_env({})
        )
    engine.dispose()


def events(service, event_type):
    return [
        json.loads(row.payload)
        for row in service.db.query(AuditOutbox).filter_by(event_type=event_type)
    ]


def test_publish_marks_change_request_and_records_policy_without_free_text(
    administration,
):
    d = document()
    marker = "secret-title-" + uuid.uuid4().hex
    draft = administration.create(d, "alice", title=marker, description=marker)
    published = administration.publish(d["id"], 1, 1, draft["generation"], "alice")
    assert published["change_request"]["status"] == "PUBLISHED"
    [event] = events(administration, "PLAYBOOK_PUBLISHED")
    assert event["change_request_id"] == draft["change_request"]["id"]
    assert event["publish_policy"] == dict(
        publish_mode="DIRECT", approvals_required=0, approver_allowlist_size=0
    )
    [evidence] = events(administration, "PROPOSAL_EVIDENCE_SNAPSHOT")
    snapshot = json.loads(evidence["snapshot_json"])
    assert snapshot["publish_policy"]["publish_mode"] == "DIRECT"
    assert snapshot["change_request_id"] == draft["change_request"]["id"]
    for row in administration.db.query(AuditOutbox):
        assert marker not in row.payload


def test_audit_failure_rolls_back_change_request_publication(administration, monkeypatch):
    d = document()
    draft = administration.create(d, "operator")

    def fail(*args, **kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr("services.playbook_administration.record_audit_event", fail)
    with pytest.raises(RuntimeError):
        administration.publish(d["id"], 1, 1, draft["generation"], "operator")
    cr = administration.repository.change_request(d["id"], draft["change_request"]["id"])
    assert (cr["status"], cr["published_revision"]) == ("OPEN", None)
    assert administration.repository.head(d["id"])["published_revision"] is None


@pytest.mark.parametrize(
    "environ, code",
    [
        ({"PLAYBOOK_PUBLISH_APPROVALS_REQUIRED": "1"}, "APPROVALS_NOT_IMPLEMENTED"),
        ({"PLAYBOOK_PUBLISH_APPROVALS_REQUIRED": "abc"}, "PUBLISH_POLICY_INVALID"),
        ({"PLAYBOOK_PUBLISH_APPROVALS_REQUIRED": "-1"}, "PUBLISH_POLICY_INVALID"),
    ],
)
def test_publication_fails_closed_unless_policy_is_direct(administration, environ, code):
    d = document()
    draft = administration.create(d, "operator")
    administration.policy = PublishPolicy.from_env(
        environ | {"PLAYBOOK_APPROVER_EMAILS": "a@example.com, A@example.com"}
    )
    assert administration.policy_view()["editable"] is False
    with pytest.raises(PlaybookConflict) as refused:
        administration.publish(d["id"], 1, 1, draft["generation"], "operator")
    assert refused.value.code == code
    assert administration.get(d["id"], 1)["status"] == "DRAFT"
    assert events(administration, "PLAYBOOK_PUBLISHED") == []
    assert administration.policy_view()["approver_allowlist_size"] == 1


def test_default_policy_is_direct_publish():
    assert PublishPolicy.from_env({}).view() == dict(
        source="environment",
        editable=False,
        approvals_required=0,
        approver_allowlist_size=0,
        publish_mode="DIRECT",
    )


def test_detail_reports_diffs_validation_and_upstream_changes_for_restores(
    administration,
):
    d = document()
    first = administration.create(d, "alice")
    administration.publish(d["id"], 1, 1, first["generation"], "alice")
    draft = administration.create_draft(d["id"], 1, first["generation"] + 1, "bob")
    administration.edit(d["id"], 2, purpose(draft, "v2"), 1, "bob")
    administration.publish(d["id"], 2, 2, draft["generation"], "bob")
    restored = administration.restore(d["id"], 1, draft["generation"] + 1, "carol")
    detail = administration.change_request_detail(d["id"], restored["change_request"]["id"])
    assert detail["head"]["published_revision"] == 2
    assert detail["base"]["revision"] == 2
    assert detail["validation"]["valid"] is True
    head_paths = {c["path"] for c in detail["diff_vs_head"]["changes"]}
    upstream = detail["upstream_changes"]
    assert (upstream["from_revision"], upstream["to_revision"]) == (1, 2)
    assert "/discovery/purpose" in head_paths & {c["path"] for c in upstream["changes"]}
    [created] = [
        e for e in events(administration, "PLAYBOOK_DRAFT_CREATED") if e["origin"] == "RESTORE"
    ]
    assert created["source_revision"] == 1
    closed = administration.close_change_request(d["id"], restored["change_request"]["id"], "carol")
    after = administration.change_request_detail(d["id"], closed["id"])
    assert after["validation"] is None and after["upstream_changes"] is None


@pytest.mark.parametrize(
    "title, description",
    [(" ", None), ("x" * 201, None), ("bad\ntitle", None), ("ok", "x" * 4001), ("ok", "\x00")],
)
def test_change_request_text_is_bounded(administration, title, description):
    with pytest.raises(RepositoryError):
        administration.create(document(), "alice", title=title, description=description)


@pytest.mark.parametrize(
    "title, description",
    [
        ("Approve \u202egnp.exe", None),  # right-to-left override
        ("Safe\u2066title\u2069", None),  # bidi isolates
        ("zero\u200bwidth", None),  # zero-width space
        ("ok", "hidden\u200d joiner"),  # zero-width joiner in a rendered description
        ("ok", "\ufeffbom"),
    ],
)
def test_change_request_text_rejects_format_characters(administration, title, description):
    d = document()
    with pytest.raises(RepositoryError):
        administration.create(d, "alice", title=title, description=description)
    created = administration.create(d, "alice", title="Plain", description="Line\nbreak")
    with pytest.raises(RepositoryError):
        administration.update_change_request(
            d["id"],
            created["change_request"]["id"],
            created["change_request"]["version"],
            "alice",
            title=title,
            description=description,
        )


@pytest.mark.parametrize("value", ["", "   ", "0", " 0 "])
def test_unset_or_zero_approvals_with_an_allowlist_is_direct_publish(value):
    policy = PublishPolicy.from_env(
        {
            "PLAYBOOK_PUBLISH_APPROVALS_REQUIRED": value,
            "PLAYBOOK_APPROVER_EMAILS": "a@example.com,b@example.com",
        }
    )
    assert policy.view()["publish_mode"] == "DIRECT"
    assert policy.view()["approvals_required"] == 0
    assert policy.view()["approver_allowlist_size"] == 2
    policy.require_direct_publish()


@pytest.mark.parametrize("value", ["1.0", "1000000", "0x0", "\u0660"])
def test_malformed_approvals_values_fail_closed(value):
    policy = PublishPolicy.from_env({"PLAYBOOK_PUBLISH_APPROVALS_REQUIRED": value})
    assert policy.view()["publish_mode"] == "INVALID"
    with pytest.raises(PlaybookConflict) as refused:
        policy.require_direct_publish()
    assert refused.value.code == "PUBLISH_POLICY_INVALID"


def test_recreate_from_head_audits_the_superseded_change_request_as_closed(
    administration,
):
    d = document()
    first = administration.create(d, "alice")
    administration.publish(d["id"], 1, 1, first["generation"], "alice")
    stale = administration.create_draft(d["id"], 1, first["generation"] + 1, "bob")
    other = administration.create_draft(d["id"], 1, stale["generation"], "carol")
    administration.publish(d["id"], other["revision"], 1, other["generation"], "carol")
    generation = administration.repository.head(d["id"])["generation"]
    recreated = administration.recreate_from_head(
        d["id"], stale["change_request"]["id"], 1, generation, "bob"
    )
    [closed] = events(administration, "PLAYBOOK_CHANGE_REQUEST_CLOSED")
    assert {
        key: closed[key]
        for key in (
            "change_request_id",
            "status",
            "reason",
            "superseded_by_change_request_id",
        )
    } == dict(
        change_request_id=stale["change_request"]["id"],
        status="CLOSED",
        reason="SUPERSEDED",
        superseded_by_change_request_id=recreated["change_request"]["id"],
    )
    created = [
        e for e in events(administration, "PLAYBOOK_DRAFT_CREATED") if e["origin"] == "RECREATE"
    ]
    assert created[0]["superseded_change_request_id"] == stale["change_request"]["id"]


@pytest.fixture
def client(administration, monkeypatch):
    from main import app
    from routers.playbooks_admin import get_administration
    from utils.auth import get_current_user
    from models.authentication import ValidatedToken

    monkeypatch.setattr("utils.auth.is_running_locally", lambda: False)
    identity = {"claims": {"sub": "operator", "email": "operator@gcp.solutions"}}
    app.dependency_overrides[get_current_user] = lambda: ValidatedToken(**identity)
    app.dependency_overrides[get_administration] = lambda: administration
    try:
        with TestClient(app) as http:
            http.identity = identity
            yield http
    finally:
        app.dependency_overrides.pop(get_administration, None)
        app.dependency_overrides.pop(get_current_user, None)


NEW_ROUTES = [
    ("GET", "/policy", None),
    ("GET", "/x/history", None),
    ("GET", "/x/change-requests", None),
    ("GET", "/x/change-requests/1", None),
    ("PATCH", "/x/change-requests/1", {"expected_version": 1, "title": "t"}),
    ("POST", "/x/change-requests/1/close", None),
    (
        "POST",
        "/x/change-requests/1/recreate-from-head",
        {"expected_draft_version": 1, "expected_generation": 1},
    ),
    ("POST", "/x/revisions/1/restore", {"expected_generation": 1}),
]


@pytest.mark.parametrize("method, path, body", NEW_ROUTES)
def test_change_request_routes_require_admin(client, method, path, body):
    client.identity["claims"] = {"sub": "customer", "email": "customer@example.com"}
    response = client.request(method, "/admin/playbooks" + path, json=body)
    assert response.status_code == 403, response.text


def test_change_request_http_contract_and_conflict_envelopes(client):
    base = "/admin/playbooks"
    assert client.get(base + "/policy").json()["publish_mode"] == "DIRECT"
    operations = client.get(base + "/capabilities").json()["operations"]
    card = next(op for op in operations if op["operation"] == "cards.issue_replacement.v1")
    assert card["contract"]["literal_bindings"] == {"issue_virtual_card": True}
    assert "card-reissue" in {p["id"] for p in card["bound_playbooks"]}
    d = document()
    created = client.post(base, json={"document": d, "title": "Launch"}).json()
    pid = d["id"]
    published = client.post(
        f"{base}/{pid}/drafts/1/publish",
        json={"expected_draft_version": 1, "expected_generation": created["generation"]},
    ).json()
    a = client.post(
        f"{base}/{pid}/drafts",
        json={"source_revision": 1, "expected_generation": published["generation"]},
    ).json()
    b = client.post(
        f"{base}/{pid}/drafts",
        json={"source_revision": 1, "expected_generation": a["generation"], "title": "B"},
    ).json()
    client.post(
        f"{base}/{pid}/drafts/{a['revision']}/publish",
        json={"expected_draft_version": 1, "expected_generation": b["generation"]},
    ).raise_for_status()
    detail = client.get(f"{base}/{pid}/change-requests/{b['change_request']['id']}").json()
    assert detail["change_request"]["behind"] is True
    behind = client.post(
        f"{base}/{pid}/drafts/{b['revision']}/publish",
        json={
            "expected_draft_version": 1,
            "expected_generation": detail["head"]["generation"],
        },
    )
    assert (behind.status_code, behind.json()["detail"]["code"]) == (409, "BEHIND_HEAD")
    recreated = client.post(
        f"{base}/{pid}/change-requests/{b['change_request']['id']}/recreate-from-head",
        json={"expected_draft_version": 1, "expected_generation": detail["head"]["generation"]},
    )
    assert recreated.status_code == 201, recreated.text
    closed_edit = client.patch(
        f"{base}/{pid}/change-requests/{b['change_request']['id']}",
        json={"expected_version": 2, "title": "late"},
    )
    assert closed_edit.json()["detail"]["code"] == "CHANGE_REQUEST_NOT_OPEN"
    assert client.patch(
        f"{base}/{pid}/change-requests/{recreated.json()['change_request']['id']}",
        json={"expected_version": 1, "title": "x" * 201},
    ).status_code == 422
    foreign = client.get(f"{base}/card-reissue/change-requests/{b['change_request']['id']}")
    assert (foreign.status_code, foreign.json()["detail"]["code"]) == (
        404,
        "CHANGE_REQUEST_NOT_FOUND",
    )
    listed = client.get(f"{base}/{pid}/change-requests", params={"status": "OPEN"}).json()
    assert [cr["title"] for cr in listed["change_requests"]] == ["B"]
    assert client.get(f"{base}/{pid}/change-requests", params={"status": "x"}).status_code == 422
    history = client.get(f"{base}/{pid}/history").json()["revisions"]
    assert [h["revision"] for h in history] == [a["revision"], 1]
    restored = client.post(
        f"{base}/{pid}/revisions/1/restore",
        json={"expected_generation": recreated.json()["generation"]},
    )
    assert restored.status_code == 201 and restored.json()["base_revision"] == a["revision"]


def test_mutating_change_request_routes_do_not_cross_playbooks(client, administration):
    base = "/admin/playbooks"
    d = document()
    created = client.post(base, json={"document": d}).json()
    pid = d["id"]
    first = client.post(
        f"{base}/{pid}/drafts/1/publish",
        json={"expected_draft_version": 1, "expected_generation": created["generation"]},
    ).json()
    second = client.post(
        f"{base}/{pid}/drafts",
        json={"source_revision": 1, "expected_generation": first["generation"]},
    ).json()
    client.post(
        f"{base}/{pid}/drafts/{second['revision']}/publish",
        json={"expected_draft_version": 1, "expected_generation": second["generation"]},
    ).raise_for_status()
    head = administration.repository.head(pid)
    open_cr = client.post(
        f"{base}/{pid}/drafts",
        json={
            "source_revision": head["published_revision"],
            "expected_generation": head["generation"],
        },
    ).json()["change_request"]
    # A second playbook with only an unpublished revision 1 owns no revision 2.
    foreign = document()
    foreign_created = client.post(base, json={"document": foreign}).json()
    before = client.get(f"{base}/{pid}/change-requests/{open_cr['id']}").json()
    attempts = [
        (
            "PATCH",
            f"{base}/card-reissue/change-requests/{open_cr['id']}",
            {"expected_version": open_cr["version"], "title": "hijack"},
            "CHANGE_REQUEST_NOT_FOUND",
        ),
        (
            "POST",
            f"{base}/card-reissue/change-requests/{open_cr['id']}/close",
            None,
            "CHANGE_REQUEST_NOT_FOUND",
        ),
        (
            "POST",
            f"{base}/card-reissue/change-requests/{open_cr['id']}/recreate-from-head",
            {"expected_draft_version": 1, "expected_generation": head["generation"] + 1},
            "CHANGE_REQUEST_NOT_FOUND",
        ),
        (
            "POST",
            f"{base}/{foreign['id']}/revisions/{second['revision']}/restore",
            {"expected_generation": foreign_created["generation"]},
            "PLAYBOOK_NOT_FOUND",
        ),
    ]
    for method, path, body, code in attempts:
        response = client.request(method, path, json=body)
        assert (response.status_code, response.json()["detail"]["code"]) == (404, code), path
    after = client.get(f"{base}/{pid}/change-requests/{open_cr['id']}").json()
    assert after["change_request"] == before["change_request"]
    assert after["draft"]["draft_version"] == before["draft"]["draft_version"]
    foreign_requests = client.get(f"{base}/{foreign['id']}/change-requests").json()
    assert [cr["revision"] for cr in foreign_requests["change_requests"]] == [1]
