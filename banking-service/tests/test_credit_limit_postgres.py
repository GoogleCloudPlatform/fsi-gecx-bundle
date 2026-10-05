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

"""Real lock/atomicity checks; requires an explicitly disposable local database."""

import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from models.action_proposal import ActionProposal
from models.audit import AuditOutbox
from models.credit_card import CreditAccount
from test_credit_limit_playbook import TABLES, seed_credit, prepare, commit, context
from services.proposal_lifecycle import ActionPreconditionError
from services.playbook_repository import bootstrap_catalog
from services.proposal_definitions import bundled_documents
from services.proposal_lifecycle import utcnow


@pytest.fixture
def postgres_credit():
    raw = os.environ.get("TEST_PROPOSAL_DATABASE_URL")
    if not raw:
        pytest.skip(
            "Set TEST_PROPOSAL_DATABASE_URL for disposable local PostgreSQL qualification"
        )
    url = make_url(raw)
    if url.host not in {"localhost", "127.0.0.1"} or not url.database.endswith(
        "_proposal_test"
    ):
        pytest.fail(
            "Proposal integration database must be localhost and end in _proposal_test"
        )
    engine = create_engine(raw)
    with engine.begin() as connection:
        for schema in ("admin", "identity", "catalog", "cards", "operations", "audit"):
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    for table in TABLES:
        table.create(engine, checkfirst=True)
    with Session(engine) as db:
        bootstrap_catalog(db, bundled_documents(), now=utcnow())
        db.commit()
        user, account, product = seed_credit(db)
        yield engine, user.auth_provider_uid, account.id
    for table in reversed(TABLES):
        table.drop(engine)
    engine.dispose()


def test_concurrent_distinct_offers_only_one_changes_original_limit(postgres_credit):
    engine, identity, account_id = postgres_credit
    with Session(engine) as db:
        from models.identity import User

        user = db.query(User).filter_by(auth_provider_uid=identity).one()
        views = [
            prepare(db, user, ctx=context(session=f"scope-{i}"), key=f"prepare-{i}")
            for i in range(2)
        ]
    barrier = threading.Barrier(2)

    def run(i):
        with Session(engine) as db:
            user = db.query(User).filter_by(auth_provider_uid=identity).one()
            barrier.wait(timeout=10)
            try:
                return commit(
                    db, user, views[i], context(session=f"scope-{i}", confirm=True)
                )["status"]
            except ActionPreconditionError:
                return "INVALIDATED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(run, range(2)))
    assert sorted(statuses) == ["COMMITTED", "INVALIDATED"]
    with Session(engine) as db:
        assert db.get(CreditAccount, account_id).credit_limit_cents == 1500000
        assert (
            db.query(AuditOutbox).filter_by(event_type="CREDIT_LIMIT_INCREASED").count()
            == 1
        )


def test_concurrent_same_proposal_serializes_and_replays(postgres_credit):
    engine, identity, account_id = postgres_credit
    from models.identity import User

    with Session(engine) as db:
        view = prepare(db, db.query(User).filter_by(auth_provider_uid=identity).one())
    barrier = threading.Barrier(2)

    def run(_):
        with Session(engine) as db:
            user = db.query(User).filter_by(auth_provider_uid=identity).one()
            barrier.wait(timeout=10)
            return commit(db, user, view)["idempotent_replay"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(run, range(2))) == [False, True]
    with Session(engine) as db:
        assert db.get(CreditAccount, account_id).available_credit_cents == 1450000
        assert (
            db.query(AuditOutbox).filter_by(event_type="CREDIT_LIMIT_INCREASED").count()
            == 1
        )


def test_real_database_archive_failure_rolls_back_all_state(
    postgres_credit, monkeypatch
):
    engine, identity, account_id = postgres_credit
    from models.identity import User
    from services import proposal_audit

    with Session(engine) as db:
        user = db.query(User).filter_by(auth_provider_uid=identity).one()
        view = prepare(db, user)
        original = proposal_audit.archive

        def fail(db, event_id, snapshot, *, recorder):
            if snapshot.get("stage") == "COMMITTED":
                raise RuntimeError("forced archive failure")
            return original(db, event_id, snapshot, recorder=recorder)

        monkeypatch.setattr(proposal_audit, "archive", fail)
        with pytest.raises(RuntimeError):
            commit(db, user, view)
    with Session(engine) as db:
        assert db.get(CreditAccount, account_id).credit_limit_cents == 1000000
        assert db.get(ActionProposal, view["proposal_id"]).status == "PROPOSED"
        assert (
            db.query(AuditOutbox).filter_by(event_type="CREDIT_LIMIT_INCREASED").count()
            == 0
        )


def test_standalone_service_refreshes_cached_account_under_lock(postgres_credit):
    engine, identity, account_id = postgres_credit
    from services.credit_card import apply_limit_increase

    with Session(engine) as caller:
        cached = caller.get(CreditAccount, account_id)
        assert cached.available_credit_cents == 950000
        with Session(engine) as spender:
            account = spender.get(CreditAccount, account_id)
            account.available_credit_cents = 800000
            spender.commit()
        result = apply_limit_increase(caller, account_id, 1500000)
        assert result["available_credit_cents"] == 1300000
    with Session(engine) as db:
        assert db.get(CreditAccount, account_id).available_credit_cents == 1300000


def test_same_provider_decision_concurrent_reservation_is_unique(postgres_credit):
    from models.identity import User
    from test_credit_limit_playbook import FakeDecisionProvider
    from services.proposal_lifecycle import ProposalPolicyError

    engine, identity, account_id = postgres_credit
    barrier = threading.Barrier(2)

    def run(index):
        provider = FakeDecisionProvider(
            mutation=lambda result: {**result, "decision_id": "shared-approval"}
        )
        with Session(engine) as db:
            user = db.query(User).filter_by(auth_provider_uid=identity).one()
            barrier.wait(timeout=10)
            try:
                prepare(
                    db,
                    user,
                    provider=provider,
                    ctx=context(session=f"reserve-{index}"),
                    key=f"key-{index}",
                )
                return "RESERVED"
            except ProposalPolicyError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(run, range(2))) == [
            "BANK_DECISION_ALREADY_BOUND",
            "RESERVED",
        ]
    with Session(engine) as db:
        assert db.query(ActionProposal).count() == 1
        assert db.get(CreditAccount, account_id).credit_limit_cents == 1000000


def test_approval_expiring_while_waiting_for_execution_lock_cannot_mutate(
    postgres_credit, monkeypatch
):
    import datetime
    from sqlalchemy import event
    from models.identity import User
    from services import decisioning
    from test_credit_limit_playbook import FakeDecisionProvider

    engine, identity, account_id = postgres_credit
    provider = FakeDecisionProvider()
    with Session(engine) as db:
        view = prepare(
            db,
            db.query(User).filter_by(auth_provider_uid=identity).one(),
            provider=provider,
        )
        receipt = db.get(ActionProposal, view["proposal_id"]).action_payload[
            "bank_decision"
        ]
    evaluated = datetime.datetime.fromisoformat(
        receipt["evaluated_at"].replace("Z", "+00:00")
    )
    expires = datetime.datetime.fromisoformat(
        receipt["expires_at"].replace("Z", "+00:00")
    )
    current = [evaluated]
    monkeypatch.setattr(decisioning, "utcnow", lambda: current[0])
    waiting = threading.Event()

    def before_execute(conn, cursor, statement, params, context, many):
        if "cards.credit_accounts" in statement and "FOR UPDATE" in statement:
            waiting.set()

    def execute():
        with Session(engine) as db:
            user = db.query(User).filter_by(auth_provider_uid=identity).one()
            with pytest.raises(ActionPreconditionError):
                commit(db, user, view, provider=provider)

    with Session(engine) as holder:
        holder.query(CreditAccount).filter_by(id=account_id).with_for_update().one()
        event.listen(engine, "before_cursor_execute", before_execute)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                task = executor.submit(execute)
                assert waiting.wait(timeout=10)
                current[0] = expires
                holder.commit()
                task.result(timeout=15)
        finally:
            holder.rollback()
            event.remove(engine, "before_cursor_execute", before_execute)
    with Session(engine) as db:
        assert db.get(CreditAccount, account_id).credit_limit_cents == 1000000
        assert db.get(ActionProposal, view["proposal_id"]).status == "INVALIDATED"
