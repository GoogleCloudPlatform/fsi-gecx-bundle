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

import datetime
import threading
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from models.playbook import Playbook, PlaybookRevision, PlaybookChangeRequest
from models.action_proposal import (
    ActionProposal,
    CONFIRMATION_POLICIES,
    PROPOSAL_STATUSES,
)
from models.fraud import FraudAlert
from models.audit import AuditOutbox
from models.identity import User
from services.action_proposal_context import ProposalRuntimeContext
from services.action_proposals import (
    ActiveProposalExistsError,
    ActionProposalService,
    CARD_REISSUE_CONTRACT_VERSION,
    FRAUD_TRIAGE_CONTRACT_VERSION,
    ProposalConflictError,
    ProposalScopeError,
    ProposalTransitionError,
    PROVISION_GOOGLE_WALLET,
    REISSUE_CARD,
    TRIAGE_FRAUD_CASE,
    WALLET_PROVISIONING_CONTRACT_VERSION,
)


CURRENT_ACTION_CONTRACTS = (
    (TRIAGE_FRAUD_CASE, FRAUD_TRIAGE_CONTRACT_VERSION),
    (REISSUE_CARD, CARD_REISSUE_CONTRACT_VERSION),
    (PROVISION_GOOGLE_WALLET, WALLET_PROVISIONING_CONTRACT_VERSION),
)

CONTRACT_PAYLOADS = {
    TRIAGE_FRAUD_CASE: {
        "fraud_alert_id": "fixture-alert",
        "money_facts": [],
        "card_last_four": "4242",
        "disputed_authorization_ids": [],
        "disputed_transaction_ids": [],
        "issue_replacement": False,
        "escalate": False,
    },
    REISSUE_CARD: {
        "account_id": "fixture-account",
        "compromised_card_id": "fixture-card",
        "reason": "LOST",
        "issue_virtual_card": True,
    },
    PROVISION_GOOGLE_WALLET: {
        "account_id": "fixture-account",
        "card_id": "fixture-card",
        "card_token": "fixture-token",
        "wallet_provider": "GOOGLE_WALLET",
    },
}

FROZEN_PROPOSAL_COLUMNS = {
    "bank_decision_ref",
    "id",
    "definition_id",
    "definition_revision",
    "definition_digest",
    "contract_version",
    "action_type",
    "status",
    "customer_id",
    "account_id",
    "support_session_id",
    "runtime_name",
    "runtime_session_id",
    "originating_customer_turn_id",
    "reset_generation",
    "confirmation_policy",
    "action_payload",
    "payload_fingerprint",
    "customer_safe_summary",
    "catalog_snapshot_id",
    "idempotency_key",
    "presented_assistant_turn_id",
    "confirmation_customer_turn_id",
    "confirmation_evidence",
    "result_payload",
    "invalidation_reason",
    "expires_at",
    "created_at",
    "updated_at",
    "presented_at",
    "confirmed_at",
    "commit_started_at",
    "completed_at",
}


@pytest.fixture(autouse=True)
def isolated_banking_money(monkeypatch):
    # Lifecycle tests use opaque fake transaction IDs. Real scoped resolution is
    # exercised by fraud workflow and Money tests, including denomination errors.
    from copy import deepcopy

    monkeypatch.setattr(
        "services.proposal_capabilities.fraud_money_facts",
        lambda repository, alert: deepcopy(alert.suspicious_transactions or []),
    )


@pytest.fixture(name="db_session")
def fixture_db_session():
    engine = create_engine("sqlite:///:memory:")
    Playbook.__table__.create(bind=engine, checkfirst=True)
    PlaybookRevision.__table__.create(bind=engine, checkfirst=True)
    PlaybookChangeRequest.__table__.create(bind=engine, checkfirst=True)
    User.__table__.create(bind=engine, checkfirst=True)
    FraudAlert.__table__.create(bind=engine, checkfirst=True)
    ActionProposal.__table__.create(bind=engine, checkfirst=True)
    AuditOutbox.__table__.create(bind=engine, checkfirst=True)
    with Session(engine) as session:
        try:
            yield session
        finally:
            session.rollback()
    AuditOutbox.__table__.drop(bind=engine)
    ActionProposal.__table__.drop(bind=engine)
    FraudAlert.__table__.drop(bind=engine)
    User.__table__.drop(bind=engine)
    PlaybookChangeRequest.__table__.drop(bind=engine, checkfirst=True)
    PlaybookRevision.__table__.drop(bind=engine, checkfirst=True)
    Playbook.__table__.drop(bind=engine, checkfirst=True)
    engine.dispose()


def _add_fraud_alert(db_session):
    user = User(
        id=uuid.uuid4(),
        auth_provider_uid="proposal-customer",
        email="proposal@example.com",
    )
    alert = FraudAlert(
        customer_id=user.id,
        auth_provider_uid="proposal-customer",
        credit_account_id=uuid.uuid4(),
        card_id=uuid.uuid4(),
        card_last_four="4242",
        status="OPEN",
        source="MODEL_DETECTED_FRAUD",
        message_thread_id="proposal-thread",
        suspicious_authorization_ids=["auth-2", "auth-1"],
        suspicious_transactions=[
            {
                "authorization_id": "auth-1",
                "merchant_name": "Corner Market",
                "money": {"amount_minor": 1299, "currency_code": "USD"},
                "billing_money": {"amount_minor": 1299, "currency_code": "USD"},
            },
            {
                "authorization_id": "auth-2",
                "transaction_id": "txn-2",
                "merchant_name": "Transit Pass",
                "money": {"amount_minor": 4500, "currency_code": "USD"},
                "billing_money": {"amount_minor": 4500, "currency_code": "USD"},
            },
        ],
    )
    db_session.add_all([user, alert])
    db_session.flush()
    return alert


@pytest.fixture(name="fraud_alert")
def fixture_fraud_alert(db_session):
    return _add_fraud_alert(db_session)


def _propose(service, alert, **overrides):
    values = {
        "customer_id": alert.customer_id,
        "fraud_alert_id": alert.id,
        "disputed_authorization_ids": ["auth-2", "auth-1", "auth-1"],
        "disputed_transaction_ids": [],
        "issue_replacement": True,
        "escalate": False,
        "support_session_id": "support-session-1",
        "runtime_name": "ADK_GEMINI_LIVE",
        "runtime_session_id": "adk-session-1",
        "originating_customer_turn_id": "customer-turn-10",
        "reset_generation": "3:9",
        "idempotency_key": "prepare-turn-10",
        "catalog_snapshot_id": "fraud-guidance-v7",
    }
    values.update(overrides)
    return service.propose_fraud_triage(**values)


def _create_contract_proposal(
    service: ActionProposalService,
    alert: FraudAlert,
    *,
    action_type: str,
    contract_version: str,
    suffix: str,
    support_session_id: str = "support-session-contract",
    expires_at: datetime.datetime | None = None,
) -> ActionProposal:
    """Create one neutral fixture through the current durable envelope seam."""
    return service._create(
        contract_version=contract_version,
        action_type=action_type,
        customer_id=alert.customer_id,
        account_id=alert.credit_account_id,
        support_session_id=support_session_id,
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="runtime-session-contract",
        originating_customer_turn_id=f"customer-origin-{suffix}",
        reset_generation="3:9",
        confirmation_policy="EXPLICIT_VERBAL",
        action_payload={**CONTRACT_PAYLOADS[action_type], "fixture": suffix},
        customer_safe_summary=f"Confirm contract fixture {suffix}.",
        catalog_snapshot_id="catalog-contract-v1",
        idempotency_key=f"contract-{suffix}",
        expires_at=expires_at,
    )


def test_durable_proposal_envelope_and_policy_values_are_frozen() -> None:
    assert {column.name for column in ActionProposal.__table__.columns} == (
        FROZEN_PROPOSAL_COLUMNS
    )
    assert PROPOSAL_STATUSES == (
        "PROPOSED",
        "PRESENTED",
        "CONFIRMED",
        "COMMITTING",
        "COMMITTED",
        "DECLINED",
        "INVALIDATED",
        "EXPIRED",
    )
    assert CONFIRMATION_POLICIES == (
        "NONE",
        "EXPLICIT_VERBAL",
        "EXPLICIT_UI",
        "STEP_UP",
        "HUMAN_APPROVAL",
    )


@pytest.mark.parametrize(("action_type", "contract_version"), CURRENT_ACTION_CONTRACTS)
def test_current_actions_share_the_frozen_exactly_once_lifecycle_contract(
    db_session,
    fraud_alert,
    action_type,
    contract_version,
):
    service = ActionProposalService(db_session)
    proposal = _create_contract_proposal(
        service,
        fraud_alert,
        action_type=action_type,
        contract_version=contract_version,
        suffix=action_type.lower(),
    )

    assert proposal.status == "PROPOSED"
    assert proposal.action_type == action_type
    assert proposal.contract_version == contract_version
    assert proposal.confirmation_policy == "EXPLICIT_VERBAL"

    service.mark_presented(proposal.id, assistant_turn_id="assistant-presentation")
    service.confirm(
        proposal.id,
        customer_turn_id="customer-decision",
        protected_evidence={
            "method": "EXPLICIT_VERBAL",
            "source": "MODEL_TOOL_INTENT",
        },
    )
    claim = service.claim_commit(
        proposal.id,
        customer_id=fraud_alert.customer_id,
        support_session_id="support-session-contract",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="runtime-session-contract",
        reset_generation="3:9",
        expected_action_type=action_type,
    )
    competing_claim = service.claim_commit(
        proposal.id,
        customer_id=fraud_alert.customer_id,
        support_session_id="support-session-contract",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="runtime-session-contract",
        reset_generation="3:9",
        expected_action_type=action_type,
    )

    assert claim.should_execute is True
    assert competing_claim.should_execute is False
    committed = service.mark_committed(
        proposal.id,
        result_payload={"success": True, "fixture": action_type},
    )
    replay = service.claim_commit(
        proposal.id,
        customer_id=fraud_alert.customer_id,
        support_session_id="support-session-contract",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="runtime-session-contract",
        reset_generation="3:9",
        expected_action_type=action_type,
    )
    assert committed.status == "COMMITTED"
    assert replay.should_execute is False
    assert replay.proposal.result_payload == {
        "success": True,
        "fixture": action_type,
    }


def test_proposal_trace_is_session_scoped_and_presenter_safe(
    db_session,
    fraud_alert,
):
    service = ActionProposalService(db_session)
    proposal = _propose(service, fraud_alert)
    service.mark_presented(proposal.id, assistant_turn_id="assistant-turn-10")
    service.confirm(
        proposal.id,
        customer_turn_id="customer-turn-11",
        protected_evidence={"source": "MODEL_TOOL_INTENT"},
    )

    trace = service.proposal_trace_for_identity(
        customer_identity="proposal-customer",
        support_session_id="support-session-1",
    )

    assert len(trace) == 1
    assert trace[0] == {
        "proposal_ref": trace[0]["proposal_ref"],
        "action_type": TRIAGE_FRAUD_CASE,
        "contract_version": FRAUD_TRIAGE_CONTRACT_VERSION,
        "status": "CONFIRMED",
        "customer_safe_summary": proposal.customer_safe_summary,
        "catalog_snapshot_ref": trace[0]["catalog_snapshot_ref"],
        "presentation_verified": True,
        "confirmation_verified": True,
        "commit_started": False,
        "created_at": proposal.created_at.isoformat(),
        "completed_at": None,
        "invalidation_reason": None,
    }
    assert trace[0]["proposal_ref"] != str(proposal.id)
    assert trace[0]["catalog_snapshot_ref"] != proposal.catalog_snapshot_id
    assert str(proposal.id) not in str(trace[0])
    assert (
        service.proposal_trace_for_identity(
            customer_identity="proposal-customer",
            support_session_id="another-session",
        )
        == []
    )


@pytest.mark.parametrize(("action_type", "contract_version"), CURRENT_ACTION_CONTRACTS)
def test_current_actions_share_expiry_and_reset_invalidation(
    db_session,
    fraud_alert,
    action_type,
    contract_version,
):
    service = ActionProposalService(db_session)
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=30
    )
    expired = _create_contract_proposal(
        service,
        fraud_alert,
        action_type=action_type,
        contract_version=contract_version,
        suffix=f"{action_type.lower()}-expired",
        expires_at=expires_at,
    )
    with pytest.raises(ProposalTransitionError, match="expired") as expired_error:
        service.mark_presented(
            expired.id,
            assistant_turn_id="assistant-too-late",
            now=expires_at + datetime.timedelta(seconds=1),
        )
    assert expired.status == "EXPIRED"
    assert expired.invalidation_reason == "PROPOSAL_EXPIRED"
    assert expired_error.value.safe_result()["error"] == "PROPOSAL_EXPIRED"
    assert expired_error.value.safe_result()["recovery_class"] == (
        "CREATE_NEW_PROPOSAL"
    )

    reset = _create_contract_proposal(
        service,
        fraud_alert,
        action_type=action_type,
        contract_version=contract_version,
        suffix=f"{action_type.lower()}-reset",
    )
    service.mark_presented(reset.id, assistant_turn_id="assistant-presentation")
    service.confirm(
        reset.id,
        customer_turn_id="customer-decision",
        protected_evidence={"source": "MODEL_TOOL_INTENT"},
    )
    with pytest.raises(ProposalScopeError, match="session reset") as reset_error:
        service.claim_commit(
            reset.id,
            customer_id=fraud_alert.customer_id,
            support_session_id="support-session-contract",
            runtime_name="ADK_GEMINI_LIVE",
            runtime_session_id="runtime-session-contract",
            reset_generation="4:0",
            expected_action_type=action_type,
        )
    assert reset.status == "INVALIDATED"
    assert reset.invalidation_reason == "RESET_GENERATION_CHANGED"
    assert reset_error.value.safe_result()["error"] == "RESET_GENERATION_CHANGED"
    assert reset_error.value.safe_result()["recovery_class"] == ("CREATE_NEW_PROPOSAL")


def test_fraud_triage_proposal_normalizes_and_binds_immutable_payload(
    db_session, fraud_alert
):
    proposal = _propose(ActionProposalService(db_session), fraud_alert)

    assert proposal.status == "PROPOSED"
    assert proposal.contract_version == "fraud-triage.v1"
    assert proposal.action_type == TRIAGE_FRAUD_CASE
    assert {
        key: value
        for key, value in proposal.action_payload.items()
        if key not in {"money_facts", "presentations", "card_last_four", "_business_input_fingerprint"}
    } == {
        "disputed_authorization_ids": ["auth-1", "auth-2"],
        "disputed_transaction_ids": [],
        "escalate": False,
        "fraud_alert_id": str(fraud_alert.id),
        "issue_replacement": True,
    }
    assert len(proposal.payload_fingerprint) == 64
    assert str(proposal.customer_id) == str(fraud_alert.customer_id)
    assert str(proposal.account_id) == str(fraud_alert.credit_account_id)
    assert proposal.action_payload["money_facts"] == fraud_alert.suspicious_transactions
    assert "presentations" not in proposal.action_payload
    assert "USD 12.99" in proposal.customer_safe_summary
    assert proposal.reset_generation == "3:9"
    assert proposal.catalog_snapshot_id == "fraud-guidance-v7"
    assert "USD 12.99 at Corner Market" in proposal.customer_safe_summary
    assert "USD 45.00 at Transit Pass" in proposal.customer_safe_summary
    assert (
        f"card ending in {fraud_alert.card_last_four}" in proposal.customer_safe_summary
    )
    assert "dispute" in proposal.customer_safe_summary.lower()
    assert "block the current card and issue a replacement" in (
        proposal.customer_safe_summary.lower()
    )


def test_proposal_creation_retries_idempotently_and_rejects_payload_drift(
    db_session, fraud_alert
):
    service = ActionProposalService(db_session)
    first = _propose(service, fraud_alert)
    replay = _propose(
        service,
        fraud_alert,
        disputed_authorization_ids=["auth-1", "auth-2"],
    )

    assert replay.id == first.id
    assert len(first.action_payload["_business_input_fingerprint"]) == 64
    assert db_session.query(ActionProposal).count() == 1

    with pytest.raises(ProposalConflictError, match="different proposal"):
        _propose(
            service,
            fraud_alert,
            disputed_authorization_ids=["auth-1"],
        )


def test_second_unresolved_proposal_is_rejected_across_action_types(
    db_session, fraud_alert
):
    service = ActionProposalService(db_session)
    active = _create_contract_proposal(
        service,
        fraud_alert,
        action_type=TRIAGE_FRAUD_CASE,
        contract_version=FRAUD_TRIAGE_CONTRACT_VERSION,
        suffix="active-fraud",
    )

    with pytest.raises(ActiveProposalExistsError) as captured:
        _create_contract_proposal(
            service,
            fraud_alert,
            action_type=REISSUE_CARD,
            contract_version=CARD_REISSUE_CONTRACT_VERSION,
            suffix="blocked-card",
        )

    assert captured.value.safe_result() == {
        "success": False,
        "error": "ACTIVE_PROPOSAL_EXISTS",
        "recovery_class": "RESOLVE_ACTIVE_PROPOSAL",
        "message": (
            "Resolve the current action proposal before proposing another action."
        ),
        "proposal_id": str(active.id),
        "action_type": TRIAGE_FRAUD_CASE,
        "status": "PROPOSED",
    }
    other_session = _create_contract_proposal(
        service,
        fraud_alert,
        action_type=REISSUE_CARD,
        contract_version=CARD_REISSUE_CONTRACT_VERSION,
        suffix="other-session-card",
        support_session_id="support-session-other",
    )
    assert other_session.status == "PROPOSED"
    assert db_session.query(ActionProposal).count() == 2


def test_database_index_rejects_active_scope_bypass(db_session, fraud_alert):
    service = ActionProposalService(db_session)
    active = _create_contract_proposal(
        service,
        fraud_alert,
        action_type=TRIAGE_FRAUD_CASE,
        contract_version=FRAUD_TRIAGE_CONTRACT_VERSION,
        suffix="index-active",
    )
    db_session.add(
        ActionProposal(
            definition_id="card-reissue",
            definition_revision=1,
            definition_digest=service.registry.require(REISSUE_CARD).definition_digest,
            contract_version=CARD_REISSUE_CONTRACT_VERSION,
            action_type=REISSUE_CARD,
            status="PROPOSED",
            customer_id=active.customer_id,
            account_id=active.account_id,
            support_session_id=active.support_session_id,
            runtime_name=active.runtime_name,
            runtime_session_id=active.runtime_session_id,
            originating_customer_turn_id="customer-index-bypass",
            reset_generation=active.reset_generation,
            confirmation_policy="EXPLICIT_VERBAL",
            action_payload=CONTRACT_PAYLOADS[REISSUE_CARD],
            payload_fingerprint="f" * 64,
            customer_safe_summary="Index bypass fixture.",
            idempotency_key="index-bypass",
            expires_at=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=60),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    "terminal_disposition",
    ("DECLINE", "REVISE", "CANCEL", "EXPIRE", "COMMIT"),
)
def test_terminal_disposition_allows_atomic_replacement_creation(
    db_session,
    fraud_alert,
    terminal_disposition,
):
    service = ActionProposalService(db_session)
    current = _create_contract_proposal(
        service,
        fraud_alert,
        action_type=TRIAGE_FRAUD_CASE,
        contract_version=FRAUD_TRIAGE_CONTRACT_VERSION,
        suffix=f"replace-{terminal_disposition.lower()}",
    )

    if terminal_disposition == "DECLINE":
        service.mark_presented(current.id, assistant_turn_id="assistant-presented")
        service.decline(current.id, customer_turn_id="customer-declined")
    elif terminal_disposition in {"REVISE", "CANCEL"}:
        service.invalidate(current.id, reason=f"CUSTOMER_{terminal_disposition}D")
    elif terminal_disposition == "EXPIRE":
        service.audit_recorder = lambda *_args, **_kwargs: None
        current.expires_at = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(seconds=1)
        db_session.flush()
    else:
        service.mark_presented(current.id, assistant_turn_id="assistant-presented")
        service.confirm(
            current.id,
            customer_turn_id="customer-confirmed",
            protected_evidence={"source": "MODEL_TOOL_INTENT"},
        )
        service.claim_commit(
            current.id,
            customer_id=fraud_alert.customer_id,
            support_session_id="support-session-contract",
            runtime_name="ADK_GEMINI_LIVE",
            runtime_session_id="runtime-session-contract",
            reset_generation="3:9",
            expected_action_type=TRIAGE_FRAUD_CASE,
        )
        service.mark_committed(current.id, result_payload={"success": True})

    replacement = _create_contract_proposal(
        service,
        fraud_alert,
        action_type=REISSUE_CARD,
        contract_version=CARD_REISSUE_CONTRACT_VERSION,
        suffix=f"replacement-{terminal_disposition.lower()}",
    )

    assert replacement.status == "PROPOSED"
    if terminal_disposition == "EXPIRE":
        assert current.status == "EXPIRED"
        assert current.invalidation_reason == "PROPOSAL_EXPIRED"
    assert db_session.query(ActionProposal).count() == 2


def test_concurrent_proposal_creation_returns_the_same_idempotent_row(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'proposal-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    Playbook.__table__.create(bind=engine, checkfirst=True)
    PlaybookRevision.__table__.create(bind=engine, checkfirst=True)
    User.__table__.create(bind=engine, checkfirst=True)
    FraudAlert.__table__.create(bind=engine, checkfirst=True)
    ActionProposal.__table__.create(bind=engine, checkfirst=True)
    AuditOutbox.__table__.create(bind=engine, checkfirst=True)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as seed_session:
        alert = _add_fraud_alert(seed_session)
        alert_id = alert.id
        seed_session.commit()

    flush_barrier = threading.Barrier(2)

    @event.listens_for(session_factory, "before_flush")
    def synchronize_proposal_inserts(session, _flush_context, _instances):
        if any(isinstance(item, ActionProposal) for item in session.new):
            flush_barrier.wait(timeout=5)

    proposal_ids = []
    errors = []

    def create_proposal():
        try:
            with session_factory() as session:
                alert = session.get(FraudAlert, alert_id)
                proposal = _propose(ActionProposalService(session), alert)
                session.commit()
                proposal_ids.append(proposal.id)
        except Exception as exc:  # pragma: no cover - assertion reports the error
            errors.append(exc)

    workers = [threading.Thread(target=create_proposal) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=15)

    event.remove(session_factory, "before_flush", synchronize_proposal_inserts)
    assert all(not worker.is_alive() for worker in workers)
    assert errors == []
    assert len(proposal_ids) == 2
    assert proposal_ids[0] == proposal_ids[1]
    with session_factory() as session:
        assert session.query(ActionProposal).count() == 1
    PlaybookRevision.__table__.drop(bind=engine, checkfirst=True)
    Playbook.__table__.drop(bind=engine, checkfirst=True)
    engine.dispose()


def test_proposal_rejects_selection_outside_customer_alert(db_session, fraud_alert):
    with pytest.raises(ProposalScopeError, match="not part of this fraud alert"):
        _propose(
            ActionProposalService(db_session),
            fraud_alert,
            disputed_authorization_ids=["auth-from-another-alert"],
        )


def test_proposal_requires_presentation_and_a_later_customer_turn(
    db_session, fraud_alert
):
    service = ActionProposalService(db_session)
    proposal = _propose(service, fraud_alert)

    with pytest.raises(ProposalTransitionError, match="expected PRESENTED"):
        service.confirm(
            proposal.id,
            customer_turn_id="customer-turn-11",
            protected_evidence={"channel": "VOICE"},
        )

    service.mark_presented(proposal.id, assistant_turn_id="assistant-turn-10")
    with pytest.raises(ProposalTransitionError, match="later real customer turn"):
        service.confirm(
            proposal.id,
            customer_turn_id="customer-turn-10",
            protected_evidence={"channel": "VOICE"},
        )

    confirmed = service.confirm(
        proposal.id,
        customer_turn_id="customer-turn-11",
        protected_evidence={
            "channel": "VOICE",
            "method": "EXPLICIT_VERBAL",
            "runtime_event_id": "event-11",
        },
    )
    assert confirmed.status == "CONFIRMED"
    assert confirmed.confirmation_customer_turn_id == "customer-turn-11"


def test_commit_claim_is_scope_bound_and_exactly_once(db_session, fraud_alert):
    service = ActionProposalService(db_session)
    proposal = _propose(service, fraud_alert)
    service.mark_presented(proposal.id, assistant_turn_id="assistant-turn-10")
    service.confirm(
        proposal.id,
        customer_turn_id="customer-turn-11",
        protected_evidence={"channel": "VOICE", "runtime_event_id": "event-11"},
    )

    with pytest.raises(ProposalScopeError, match="does not belong"):
        service.claim_commit(
            proposal.id,
            customer_id=uuid.uuid4(),
            support_session_id="support-session-1",
            runtime_name="ADK_GEMINI_LIVE",
            runtime_session_id="adk-session-1",
            reset_generation="3:9",
            expected_action_type=TRIAGE_FRAUD_CASE,
        )

    first_claim = service.claim_commit(
        proposal.id,
        customer_id=fraud_alert.customer_id,
        support_session_id="support-session-1",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="adk-session-1",
        reset_generation="3:9",
        expected_action_type=TRIAGE_FRAUD_CASE,
    )
    assert first_claim.should_execute is True
    assert first_claim.proposal.status == "COMMITTING"

    concurrent_claim = service.claim_commit(
        proposal.id,
        customer_id=fraud_alert.customer_id,
        support_session_id="support-session-1",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="adk-session-1",
        reset_generation="3:9",
        expected_action_type=TRIAGE_FRAUD_CASE,
    )
    assert concurrent_claim.should_execute is False

    committed = service.mark_committed(
        proposal.id,
        result_payload={"success": True, "fraud_alert_id": str(fraud_alert.id)},
    )
    assert committed.status == "COMMITTED"

    replay = service.claim_commit(
        proposal.id,
        customer_id=fraud_alert.customer_id,
        support_session_id="support-session-1",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="adk-session-1",
        reset_generation="3:9",
        expected_action_type=TRIAGE_FRAUD_CASE,
    )
    assert replay.should_execute is False
    assert replay.proposal.result_payload["success"] is True


def test_reset_generation_change_invalidates_confirmed_proposal(
    db_session, fraud_alert
):
    service = ActionProposalService(db_session)
    proposal = _propose(service, fraud_alert)
    service.mark_presented(proposal.id, assistant_turn_id="assistant-turn-10")
    service.confirm(
        proposal.id,
        customer_turn_id="customer-turn-11",
        protected_evidence={"channel": "VOICE", "runtime_event_id": "event-11"},
    )

    with pytest.raises(ProposalScopeError, match="session reset"):
        service.claim_commit(
            proposal.id,
            customer_id=fraud_alert.customer_id,
            support_session_id="support-session-1",
            runtime_name="ADK_GEMINI_LIVE",
            runtime_session_id="adk-session-1",
            reset_generation="4:0",
            expected_action_type=TRIAGE_FRAUD_CASE,
        )
    assert proposal.status == "INVALIDATED"
    assert proposal.invalidation_reason == "RESET_GENERATION_CHANGED"

    disposition = service.proposal_disposition_for_identity(
        proposal.id,
        customer_identity="proposal-customer",
        runtime_context=ProposalRuntimeContext(
            support_session_id="support-session-1",
            runtime_name="ADK_GEMINI_LIVE",
            runtime_session_id="adk-session-1",
            customer_turn_id="customer-turn-12",
            reset_generation="4:0",
        ),
    )
    assert disposition == {
        "proposal_id": str(proposal.id),
        "action_type": TRIAGE_FRAUD_CASE,
        "contract_version": "fraud-triage.v1",
        "status": "INVALIDATED",
        "invalidation_reason": "RESET_GENERATION_CHANGED",
    }


def test_disposition_lookup_remains_bound_to_trusted_session(db_session, fraud_alert):
    service = ActionProposalService(db_session)
    proposal = _propose(service, fraud_alert)

    with pytest.raises(ProposalScopeError, match="runtime session"):
        service.proposal_disposition_for_identity(
            proposal.id,
            customer_identity="proposal-customer",
            runtime_context=ProposalRuntimeContext(
                support_session_id="another-support-session",
                runtime_name="ADK_GEMINI_LIVE",
                runtime_session_id="adk-session-1",
                customer_turn_id="customer-turn-12",
                reset_generation="3:9",
            ),
        )


def test_expired_proposal_cannot_be_presented(db_session, fraud_alert):
    service = ActionProposalService(db_session)
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=30
    )
    proposal = _propose(service, fraud_alert, expires_at=expires_at)

    with pytest.raises(ProposalTransitionError, match="expired"):
        service.mark_presented(
            proposal.id,
            assistant_turn_id="assistant-turn-late",
            now=expires_at + datetime.timedelta(seconds=1),
        )
    assert proposal.status == "EXPIRED"


def test_authenticated_adapter_binds_transport_scope_and_returns_safe_view(
    db_session, fraud_alert
):
    context = ProposalRuntimeContext(
        support_session_id="support-session-1",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="adk-session-1",
        customer_turn_id="customer-turn-10",
        reset_generation="3:9",
        catalog_snapshot_id="fraud-guidance-v7",
    )

    result = ActionProposalService(db_session).propose_fraud_triage_for_identity(
        customer_identity="proposal-customer",
        fraud_alert_id=fraud_alert.id,
        disputed_authorization_ids=["auth-1"],
        disputed_transaction_ids=[],
        issue_replacement=True,
        escalate=False,
        runtime_context=context,
        idempotency_key="adapter-turn-10",
    )

    proposal = db_session.query(ActionProposal).one()
    assert result["proposal_id"] == str(proposal.id)
    assert result["customer_safe_summary"] == proposal.customer_safe_summary
    assert result["display_selection"]["disputed_authorization_ids"] == ["auth-1"]
    assert proposal.customer_id == fraud_alert.customer_id
    assert proposal.support_session_id == "support-session-1"


def test_authenticated_commit_adapter_records_protected_later_turn_evidence(
    db_session, fraud_alert, monkeypatch
):
    service = ActionProposalService(db_session)
    proposal = _propose(service, fraud_alert)
    context = ProposalRuntimeContext(
        support_session_id="support-session-1",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="adk-session-1",
        customer_turn_id="customer-turn-11",
        reset_generation="3:9",
        presentation_turn_id="assistant-turn-10",
        confirmation_turn_id="customer-turn-11",
        confirmation_method="EXPLICIT_VERBAL",
        confirmation_source="MODEL_TOOL_INTENT",
    )
    monkeypatch.setattr(
        service,
        "commit_fraud_triage",
        lambda *args, **kwargs: {"success": True, "status": "COMMITTED"},
    )

    result = service.commit_fraud_triage_for_identity(
        proposal.id,
        customer_identity="proposal@example.com",
        runtime_context=context,
    )

    assert result["success"] is True
    assert proposal.status == "CONFIRMED"
    assert proposal.presented_assistant_turn_id == "assistant-turn-10"
    assert proposal.confirmation_customer_turn_id == "customer-turn-11"
    assert proposal.confirmation_evidence["method"] == "EXPLICIT_VERBAL"


def test_missing_presentation_evidence_returns_typed_recovery(db_session, fraud_alert):
    service = ActionProposalService(db_session)
    proposal = _propose(service, fraud_alert)
    context = ProposalRuntimeContext(
        support_session_id="support-session-1",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="adk-session-1",
        customer_turn_id="customer-turn-11",
        reset_generation="3:9",
    )

    with pytest.raises(ProposalTransitionError) as captured:
        service.commit_fraud_triage_for_identity(
            proposal.id,
            customer_identity="proposal-customer",
            runtime_context=context,
        )

    assert captured.value.safe_result() == {
        "success": False,
        "error": "PRESENTATION_EVIDENCE_REQUIRED",
        "recovery_class": "REPRESENT_AND_RECONFIRM",
        "message": (
            "Present the current proposal again and obtain a later explicit "
            "customer decision."
        ),
        "proposal_id": str(proposal.id),
        "action_type": TRIAGE_FRAUD_CASE,
        "status": "PROPOSED",
    }


def test_committing_without_durable_result_returns_typed_retry_disposition(
    db_session, fraud_alert
):
    service = ActionProposalService(db_session)
    proposal = _create_contract_proposal(
        service,
        fraud_alert,
        action_type=REISSUE_CARD,
        contract_version=CARD_REISSUE_CONTRACT_VERSION,
        suffix="commit-pending",
    )
    service.mark_presented(proposal.id, assistant_turn_id="assistant-presented")
    service.confirm(
        proposal.id,
        customer_turn_id="customer-confirmed",
        protected_evidence={"source": "MODEL_TOOL_INTENT"},
    )
    service.claim_commit(
        proposal.id,
        customer_id=fraud_alert.customer_id,
        support_session_id="support-session-contract",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="runtime-session-contract",
        reset_generation="3:9",
        expected_action_type=REISSUE_CARD,
    )

    result = service.execute_registered_commit(
        proposal.id,
        customer_id=fraud_alert.customer_id,
        support_session_id="support-session-contract",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="runtime-session-contract",
        reset_generation="3:9",
        expected_action_type=REISSUE_CARD,
    )

    assert result["error"] == "COMMIT_RESULT_PENDING"
    assert result["recovery_class"] == "RETRY_SAME_PROPOSAL"
    assert result["status"] == "COMMITTING"


def _runtime_context(*, customer_turn_id="customer-turn-10", confirming=False):
    values = {
        "support_session_id": "support-session-1",
        "runtime_name": "ADK_GEMINI_LIVE",
        "runtime_session_id": "adk-session-1",
        "customer_turn_id": customer_turn_id,
        "reset_generation": "3:9",
        "catalog_snapshot_id": "support-guidance-v8",
    }
    if confirming:
        values.update(
            {
                "presentation_turn_id": "assistant-turn-10",
                "confirmation_turn_id": customer_turn_id,
                "confirmation_method": "EXPLICIT_VERBAL",
                "confirmation_source": "MODEL_TOOL_INTENT",
            }
        )
    return ProposalRuntimeContext(**values)


def _mock_card_repository(monkeypatch, fraud_alert):
    account = SimpleNamespace(id=fraud_alert.credit_account_id)
    card = SimpleNamespace(
        id=fraud_alert.card_id,
        account_id=account.id,
        status="ACTIVE",
        is_active=True,
        is_virtual=True,
        last_four="4242",
        card_token="replacement-token",
    )
    repository = SimpleNamespace(
        get_account_by_customer=lambda _customer_id: account,
        list_cards_by_account=lambda _account_id: [card],
    )
    monkeypatch.setattr(
        "services.proposal_capabilities.CreditCardRepository",
        lambda _db: repository,
    )
    return account, card


def test_card_reissue_uses_generic_proposal_commit_protocol(
    db_session, fraud_alert, monkeypatch
):
    _, card = _mock_card_repository(monkeypatch, fraud_alert)
    monkeypatch.setattr(
        "services.proposal_capabilities.issue_replacement_card",
        lambda *_args, **_kwargs: {
            "success": True,
            "message": "Replacement virtual card issued.",
            "old_card_id": str(card.id),
            "new_card_id": str(uuid.uuid4()),
            "new_card_token": "new-token",
            "new_last_four": "9876",
            "replacement_status": "ISSUED",
            "status": "ACTIVE",
            "is_virtual": True,
        },
    )
    service = ActionProposalService(db_session)
    proposed = service.propose_card_reissue_for_identity(
        customer_identity="proposal-customer",
        runtime_context=_runtime_context(),
        reason="stolen",
        idempotency_key="card-reissue-turn-10",
    )

    assert proposed["action_type"] == REISSUE_CARD
    assert proposed["display_selection"] == {
        "reason": "STOLEN",
        "issue_virtual_card": True,
    }
    assert "ending 4242" in proposed["customer_safe_summary"]
    assert "block the card" in proposed["customer_safe_summary"]
    assert "replacement virtual card" in proposed["customer_safe_summary"]

    committed = service.commit_card_reissue_for_identity(
        proposed["proposal_id"],
        customer_identity="proposal-customer",
        runtime_context=_runtime_context(
            customer_turn_id="customer-turn-11", confirming=True
        ),
    )
    proposal = db_session.get(ActionProposal, uuid.UUID(proposed["proposal_id"]))
    assert committed["status"] == "COMMITTED"
    assert committed["replacement_card"]["new_last_four"] == "9876"
    assert proposal.confirmation_evidence["source"] == "MODEL_TOOL_INTENT"


def test_wallet_provisioning_uses_generic_proposal_commit_protocol(
    db_session, fraud_alert, monkeypatch
):
    _mock_card_repository(monkeypatch, fraud_alert)
    observed = {}

    def fake_queue(*_args, **kwargs):
        observed.update(kwargs)
        return {
            "message": "Digital wallet provisioning queued successfully.",
            "card_token": "replacement-token",
            "wallet_provider": "GOOGLE_WALLET",
            "wallet_provisioning_status": "QUEUED",
        }

    monkeypatch.setattr(
        "services.proposal_capabilities.queue_wallet_provisioning", fake_queue
    )
    service = ActionProposalService(db_session)
    proposed = service.propose_wallet_provisioning_for_identity(
        customer_identity="proposal-customer",
        runtime_context=_runtime_context(),
        idempotency_key="wallet-turn-10",
    )

    assert proposed["action_type"] == PROVISION_GOOGLE_WALLET
    assert proposed["display_selection"] == {"wallet_provider": "GOOGLE_WALLET"}
    assert "ending 4242" in proposed["customer_safe_summary"]
    assert "queue" in proposed["customer_safe_summary"]
    assert "Google Wallet" in proposed["customer_safe_summary"]

    committed = service.commit_wallet_provisioning_for_identity(
        proposed["proposal_id"],
        customer_identity="proposal-customer",
        runtime_context=_runtime_context(
            customer_turn_id="customer-turn-11", confirming=True
        ),
    )
    assert committed["status"] == "COMMITTED"
    assert committed["wallet_provisioning_status"] == "QUEUED"
    assert observed["commit_transaction"] is False


@pytest.mark.parametrize(
    ("decision", "expected_status", "expected_reason"),
    (
        ("DECLINE", "DECLINED", "CUSTOMER_DECLINED"),
        ("REVISE", "INVALIDATED", "CUSTOMER_REVISED"),
        ("CANCEL", "INVALIDATED", "CUSTOMER_CANCELLED"),
    ),
)
def test_non_commit_decisions_use_the_same_protected_proposal_protocol(
    db_session,
    fraud_alert,
    monkeypatch,
    decision,
    expected_status,
    expected_reason,
):
    monkeypatch.setattr(
        "services.action_proposals.record_audit_event",
        lambda *_args, **_kwargs: None,
    )
    service = ActionProposalService(db_session)
    proposal = _propose(service, fraud_alert)
    context = _runtime_context(
        customer_turn_id="customer-turn-11",
        confirming=True,
    )

    result = service.decide_for_identity(
        proposal.id,
        decision=decision,
        customer_identity="proposal-customer",
        runtime_context=context,
    )

    assert result["decision"] == decision
    assert result["status"] == expected_status
    assert proposal.invalidation_reason == expected_reason
    assert proposal.confirmation_customer_turn_id == "customer-turn-11"
    replay = service.decide_for_identity(
        proposal.id,
        decision=decision,
        customer_identity="proposal-customer",
        runtime_context=context,
    )
    assert replay["idempotent_replay"] is True
    with pytest.raises(ProposalTransitionError):
        service.claim_commit(
            proposal.id,
            customer_id=fraud_alert.customer_id,
            support_session_id="support-session-1",
            runtime_name="ADK_GEMINI_LIVE",
            runtime_session_id="adk-session-1",
            reset_generation="3:9",
            expected_action_type=TRIAGE_FRAUD_CASE,
        )


def test_non_commit_decision_requires_current_scope_and_later_turn(
    db_session,
    fraud_alert,
):
    service = ActionProposalService(db_session)
    proposal = _propose(service, fraud_alert)
    db_session.commit()

    with pytest.raises(ProposalScopeError):
        service.decide_for_identity(
            proposal.id,
            decision="DECLINE",
            customer_identity="proposal-customer",
            runtime_context=ProposalRuntimeContext(
                support_session_id="wrong-session",
                runtime_name="ADK_GEMINI_LIVE",
                runtime_session_id="adk-session-1",
                customer_turn_id="customer-turn-11",
                reset_generation="3:9",
                presentation_turn_id="assistant-turn-10",
                confirmation_turn_id="customer-turn-11",
                confirmation_method="EXPLICIT_VERBAL",
                confirmation_source="MODEL_TOOL_INTENT",
            ),
        )

    with pytest.raises(ProposalTransitionError, match="later customer turn"):
        service.decide_for_identity(
            proposal.id,
            decision="REVISE",
            customer_identity="proposal-customer",
            runtime_context=ProposalRuntimeContext(
                support_session_id="support-session-1",
                runtime_name="ADK_GEMINI_LIVE",
                runtime_session_id="adk-session-1",
                customer_turn_id="customer-turn-10",
                reset_generation="3:9",
                presentation_turn_id="assistant-turn-10",
                confirmation_turn_id="customer-turn-10",
                confirmation_method="EXPLICIT_VERBAL",
                confirmation_source="MODEL_TOOL_INTENT",
            ),
        )


def test_new_definition_executes_and_replays_through_pinned_revision(
    db_session, fraud_alert, monkeypatch
):
    import json
    from copy import deepcopy
    from services.proposal_definitions import CATALOG_PATH, load_action_registry

    _mock_card_repository(monkeypatch, fraud_alert)
    calls = []

    def replace(*args, **kwargs):
        calls.append(kwargs)
        return {"message": "Issued", "success": True}

    monkeypatch.setattr(
        "services.proposal_capabilities.issue_replacement_card", replace
    )
    first = json.loads((CATALOG_PATH / "card-reissue.v2.json").read_text())
    first.update(id="replacement-followup", action_type="REPLACEMENT_FOLLOWUP", revision=1)
    from services.playbook_administration import PlaybookAdministration
    admin = PlaybookAdministration(db_session)
    draft = admin.create(first, "operator")
    admin.publish(first["id"], 1, 1, draft["generation"], "operator")
    service = ActionProposalService(db_session)
    service.registry = load_action_registry(db_session, [first])
    context = dict(
        support_session_id="new-definition",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="runtime",
        originating_customer_turn_id="origin",
        reset_generation="1",
        idempotency_key="request",
    )
    proposal = service.propose_action(
        action_type=first["action_type"],
        customer_id=fraud_alert.customer_id,
        inputs={"reason": "LOST"},
        **context,
    )
    second = deepcopy(first)
    second["revision"] = 2
    second["presentation"]["template"] += " Please confirm."
    service.registry = load_action_registry(db_session, [first, second])
    replay = service.propose_action(
        action_type=first["action_type"],
        customer_id=fraud_alert.customer_id,
        inputs={"reason": "LOST"},
        **context,
    )
    assert replay.id == proposal.id
    assert replay.definition_revision == 1
    service.mark_presented(proposal.id, assistant_turn_id="presentation")
    service.confirm(
        proposal.id,
        customer_turn_id="decision",
        protected_evidence={"method": "EXPLICIT_VERBAL", "source": "MODEL_TOOL_INTENT"},
    )
    commit = dict(
        customer_id=fraud_alert.customer_id,
        support_session_id="new-definition",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="runtime",
        reset_generation="1",
        expected_action_type=first["action_type"],
    )
    assert (
        service.execute_registered_commit(proposal.id, **commit)["status"]
        == "COMMITTED"
    )
    assert service.execute_registered_commit(proposal.id, **commit)["idempotent_replay"]
    assert len(calls) == 1
    assert calls[0]["commit_transaction"] is False


def test_discovered_fourth_playbook_prepares_commits_and_replays_with_generic_tools(
    db_session, fraud_alert, monkeypatch
):
    import json
    from services.proposal_definitions import CATALOG_PATH, load_action_registry
    from services.playbook_discovery import discover_playbooks

    _mock_card_repository(monkeypatch, fraud_alert)
    calls = []

    def replace(*args, **kwargs):
        calls.append(kwargs)
        return {"message": "Issued", "success": True}

    monkeypatch.setattr(
        "services.proposal_capabilities.issue_replacement_card", replace
    )
    document = json.loads((CATALOG_PATH / "card-reissue.v2.json").read_text())
    document.update(id="new-replacement", action_type="NEW_REPLACEMENT", revision=1)
    from services.playbook_administration import PlaybookAdministration
    admin = PlaybookAdministration(db_session)
    draft = admin.create(document, "operator")
    admin.publish(document["id"], 1, draft["draft_version"], draft["generation"], "operator")
    service = ActionProposalService(db_session)
    service.registry = load_action_registry(db_session, [document])
    found = discover_playbooks(service.registry, "My card is damaged")["playbooks"][0]
    request = dict(
        playbook_id=found["playbook_id"],
        revision=found["revision"],
        digest=found["digest"],
        inputs={"reason": "DAMAGED"},
        customer_identity="proposal-customer",
        runtime_context=_runtime_context(),
        idempotency_key="generic-1",
    )
    proposed = service.prepare_playbook_for_identity(**request)
    assert proposed["action_type"] == "NEW_REPLACEMENT"
    assert not calls
    with pytest.raises(ProposalTransitionError):
        service.commit_action_for_identity(
            proposed["proposal_id"],
            customer_identity="proposal-customer",
            runtime_context=_runtime_context(),
        )
    with pytest.raises(ProposalScopeError):
        service.commit_action_for_identity(
            proposed["proposal_id"],
            customer_identity="someone-else",
            runtime_context=_runtime_context(
                customer_turn_id="customer-turn-11", confirming=True
            ),
        )
    draft = admin.create_draft(document["id"], 1, 2, "operator")
    admin.publish(document["id"], draft["revision"], draft["draft_version"], draft["generation"], "operator")
    service.registry = load_action_registry(db_session)
    assert (
        service.prepare_playbook_for_identity(**request)["proposal_id"]
        == proposed["proposal_id"]
    )
    from services.action_proposals import ProposalError

    with pytest.raises(ProposalError, match="published playbook changed"):
        service.prepare_playbook_for_identity(
            **dict(request, idempotency_key="new-request")
        )
    commit = dict(
        customer_identity="proposal-customer",
        runtime_context=_runtime_context(
            customer_turn_id="customer-turn-11", confirming=True
        ),
    )
    assert (
        service.commit_action_for_identity(proposed["proposal_id"], **commit)["status"]
        == "COMMITTED"
    )
    assert service.commit_action_for_identity(proposed["proposal_id"], **commit)[
        "idempotent_replay"
    ]
    assert len(calls) == 1


def test_generic_fraud_preparation_rejects_incomplete_review(
    db_session, fraud_alert, monkeypatch
):
    from services.action_proposals import ProposalError

    service = ActionProposalService(db_session)
    spec = service.registry.published("fraud-triage")
    monkeypatch.setattr(
        "services.fraud_alerts.FraudAlertService.review_open_alert_selection",
        lambda *a, **k: {"success": True, "ready_to_propose": False},
    )
    with pytest.raises(ProposalError, match="Complete the fraud selection"):
        service.prepare_playbook_for_identity(
            playbook_id=spec.definition_id,
            revision=spec.definition_revision,
            digest=spec.definition_digest,
            inputs={
                "fraud_alert_id": str(fraud_alert.id),
                "selection_status": "PARTIAL",
                "disputed_authorization_ids": ["auth-1"],
                "disputed_transaction_ids": [],
                "recognized_authorization_ids": [],
                "recognized_transaction_ids": [],
                "issue_replacement": True,
                "escalate": False,
            },
            customer_identity="proposal-customer",
            runtime_context=_runtime_context(),
            idempotency_key="partial",
        )
    assert db_session.query(ActionProposal).count() == 0


def test_generic_fraud_preparation_accepts_complete_recognized_activity(
    db_session, fraud_alert
):
    service = ActionProposalService(db_session)
    spec = service.registry.published("fraud-triage")
    result = service.prepare_playbook_for_identity(
        playbook_id=spec.definition_id,
        revision=spec.definition_revision,
        digest=spec.definition_digest,
        inputs={
            "fraud_alert_id": str(fraud_alert.id),
            "selection_status": "COMPLETE",
            "disputed_authorization_ids": [],
            "disputed_transaction_ids": [],
            "recognized_authorization_ids": ["auth-1", "auth-2"],
            "recognized_transaction_ids": ["txn-2"],
            "issue_replacement": False,
            "escalate": False,
        },
        customer_identity="proposal-customer",
        runtime_context=_runtime_context(),
        idempotency_key="recognized",
    )
    assert result["status"] == "PROPOSED"
    assert result["display_selection"]["disputed_authorization_ids"] == []
    assert result["display_selection"]["issue_replacement"] is False
    assert fraud_alert.status == "OPEN"


@pytest.mark.parametrize(
    "extra", [{"customer_id": "other"}, {"card_token": "injected"}]
)
def test_generic_prepare_rejects_scope_and_private_business_input(
    db_session, fraud_alert, monkeypatch, extra
):
    from services.action_proposals import ProposalError

    _mock_card_repository(monkeypatch, fraud_alert)
    service = ActionProposalService(db_session)
    spec = service.registry.published("google-wallet-provisioning")
    with pytest.raises(ProposalError, match="Business inputs"):
        service.prepare_playbook_for_identity(
            playbook_id=spec.definition_id,
            revision=spec.definition_revision,
            digest=spec.definition_digest,
            inputs=extra,
            customer_identity="proposal-customer",
            runtime_context=_runtime_context(),
            idempotency_key="injection",
        )
    assert db_session.query(ActionProposal).count() == 0


def test_fraud_preparation_is_independent_of_decisioning_configuration(db_session, fraud_alert, monkeypatch):
    from services import decisioning
    def unavailable():
        raise ValueError("invalid decisioning config")
    monkeypatch.setattr(decisioning, "load_decisioning_provider", unavailable)
    assert _propose(ActionProposalService(db_session), fraud_alert).status == "PROPOSED"


# --- Tiered credit-limit contracts: legacy wire and audit compatibility -----

LEGACY_NOW = datetime.datetime(2026, 10, 2, tzinfo=datetime.timezone.utc)
LEGACY_ACCOUNT = "4b0b3f4e-7c1a-4d55-9a37-1d2f0e6a9b11"
# Computed against origin/main (e1baae9) before the tiered contract landed.
# A change here means a CES/ADK-visible payload, a payload fingerprint, the
# proposal-evidence.v1 snapshot or the proposal-audit.v2 event changed shape:
# bump the contract version deliberately instead of updating these values.
# (Lane 2's CREDIT_LIMIT_POLICY change will legitimately move all of them.)
LEGACY_WIRE_DIGESTS = {
    "decision_request": "70322006e36eea02718b3a862d4e9cc2e91b73be7c9f0204b3b49196f2ce3467",
    "bank_decision": "dd90fe2a28b57bf4c8c29459b1d3df7ec4c4d891dcc9afecce1a310e10b9b771",
    "payload_fingerprint": "4b58d8485b5b3aacf17ac05fc816511a3c6d54568ff25de275a1408d050308bc",
    "evidence_snapshot": "82a9f4517197b8ddf3ea4bcc60c8060db2c2739e31bbc67f033101eb798715a6",
    "audit_events": "511f76d2eb2607683f5d823ebac26354e1eadc27ae945950763284ff41e14265",
}


def _wire_sha(value):
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _legacy_credit_limit_proposal():
    from models.money import Money
    from services.credit_card import CREDIT_LIMIT_POLICY
    from services.decisioning import DecisionRequest, digest, load_decisioning_provider
    from services.proposal_definitions import load_action_registry
    from services.proposal_lifecycle import canonical_payload

    facts = {
        "account_id": LEGACY_ACCOUNT, "account_status": "ACTIVE", "currency_code": "USD",
        "product_code": "DEMO", "current_limit_minor": 1000000, "product_active": True,
        "minimum_limit_minor": 100000, "maximum_limit_minor": 3000000,
    }
    requested = {"amount_minor": 1500000, "currency_code": "USD"}
    request = DecisionRequest(
        request_ref="a" * 64,
        scope_ref="b" * 64,
        input_ref=digest({"facts": facts, "requested_limit": requested}),
        requested_limit=Money.model_validate(requested),
        facts=facts,
    )
    decision = load_decisioning_provider(
        scenario="STANDARD", clock=lambda: LEGACY_NOW
    ).evaluate(request)
    payload = {
        "account_id": LEGACY_ACCOUNT,
        "current_limit": {"amount_minor": 1000000, "currency_code": "USD"},
        "proposed_limit": requested,
        "increase_amount": {"amount_minor": 500000, "currency_code": "USD"},
        "credit_limit_policy": dict(CREDIT_LIMIT_POLICY),
        "eligibility_facts": facts,
        "prepared_arithmetic": {
            "available_credit_minor": 950000, "projected_available_credit_minor": 1450000,
        },
        "bank_decision": decision.model_dump(mode="json"),
        "decision_request": request.model_dump(mode="json"),
        "approval_semantics": "DEMO_APPROVED_ON_CONFIRMATION",
    }
    proposal = SimpleNamespace(
        id=uuid.UUID("0e4c1d7a-3b8e-4f21-a6d9-5c2b7e1f9a30"), status="CONFIRMED",
        invalidation_reason=None, customer_id=uuid.UUID("7d9e2a41-5f3c-4b8a-9e16-2c4d8f0b3a57"),
        account_id=uuid.UUID(LEGACY_ACCOUNT), support_session_id="support-limit",
        runtime_name="ADK_GEMINI_LIVE", runtime_session_id="runtime-support-limit",
        reset_generation="reset-1", originating_customer_turn_id="turn-1",
        catalog_snapshot_id="guidance-2.9",
        customer_safe_summary="Increase your credit limit from $10,000.00 to $15,000.00.",
        action_payload=payload, payload_fingerprint=canonical_payload(payload)[1],
        confirmation_evidence={
            "method": "EXPLICIT_VERBAL", "source": "MODEL_TOOL_INTENT",
            "runtime_name": "ADK_GEMINI_LIVE", "runtime_session_id": "runtime-support-limit",
            "presentation_turn_id": "assistant-1", "confirmation_turn_id": "turn-2",
            "acknowledged_fact_keys": ["current_limit", "proposed_limit"],
        },
        result_payload=None, action_type="CREDIT_LIMIT_INCREASE",
        contract_version="credit-limit-increase.v1",
        presented_assistant_turn_id="assistant-1", confirmation_customer_turn_id="turn-2",
        created_at=LEGACY_NOW, expires_at=LEGACY_NOW + datetime.timedelta(minutes=5),
        presented_at=LEGACY_NOW, confirmed_at=LEGACY_NOW, commit_started_at=None,
        completed_at=None,
    )
    spec = load_action_registry(None).published("credit-limit-increase")
    return request, decision, proposal, spec


class _NoPriorAuditEvents:
    def query(self, *_):
        return self

    def filter(self, *_):
        return self

    def first(self):
        return None


def test_existing_credit_limit_wire_evidence_and_audit_are_byte_identical(monkeypatch):
    from services.proposal_audit import record_transition
    from services.proposal_evidence import transition_snapshot

    monkeypatch.setenv("LOG_REFERENCE_SALT", "fsi-gecx-log-reference")
    request, decision, proposal, spec = _legacy_credit_limit_proposal()
    events = []
    record_transition(
        _NoPriorAuditEvents(), proposal, spec, "CONFIRMED",
        recorder=lambda db, event_type, payload, **kw: events.append([event_type, payload, kw]),
    )
    assert {
        "decision_request": _wire_sha(request.model_dump(mode="json")),
        "bank_decision": _wire_sha(decision.model_dump(mode="json")),
        "payload_fingerprint": proposal.payload_fingerprint,
        "evidence_snapshot": _wire_sha(transition_snapshot(proposal, spec, "CONFIRMED")),
        "audit_events": _wire_sha(events),
    } == LEGACY_WIRE_DIGESTS


@pytest.mark.parametrize("outcome", ["COUNTEROFFER", "INVENTED_OUTCOME"])
def test_policy_refusal_for_new_or_unknown_outcome_uses_generic_safe_message(outcome):
    from services.proposal_lifecycle import ProposalPolicyError
    from services.proposal_protocol import PolicyEvaluationEvidence

    error = ProposalPolicyError(
        PolicyEvaluationEvidence(
            policy={}, facts={}, requested_limit={},
            reason_code="COUNTEROFFER_AVAILABLE", bank_decision={"outcome": outcome},
        )
    )
    assert error.customer_message == (
        "This requested credit-limit increase is not eligible under the demo policy."
    )


def _consent_evidence(inquiry_type="SOFT", **changes):
    consent = {
        "inquiry_type": inquiry_type,
        "disclosure_version": f"{inquiry_type.lower()}-inquiry-disclosure.v1",
        "consent_turn_id": "turn-7",
    }
    consent.update(changes)
    return {"runtime_session_id": "runtime-1", "inquiry_consent": consent}


def test_soft_consent_evidence_cannot_stand_in_for_hard_consent():
    from services.decisioning import InquiryConsent
    from services.proposal_evidence import consent_evidence_ref

    soft_ref = consent_evidence_ref(_consent_evidence("SOFT"), "a" * 64)
    hard_ref = consent_evidence_ref(_consent_evidence("HARD"), "a" * 64)
    assert soft_ref != hard_ref
    # Consent is bound to its originating request, not reusable in the session.
    assert consent_evidence_ref(_consent_evidence("SOFT"), "b" * 64) != soft_ref
    with pytest.raises(ValueError):
        consent_evidence_ref(
            _consent_evidence("HARD", disclosure_version="soft-inquiry-disclosure.v1"),
            "a" * 64,
        )
    with pytest.raises(ValueError):
        InquiryConsent(
            inquiry_type="HARD",
            disclosure_version="soft-inquiry-disclosure.v1",
            consent_ref=soft_ref,
        )


@pytest.mark.parametrize(
    "evidence",
    [
        None,
        {"runtime_session_id": "runtime-1"},
        _consent_evidence("NONE"),
        _consent_evidence(consent_turn_id=""),
        _consent_evidence(secret="private"),
        _consent_evidence(disclosure_version="soft-inquiry-disclosure.v1 plus anything"),
        _consent_evidence(disclosure_version="soft-inquiry-disclosure.v1" + "0" * 5000),
        {**_consent_evidence(), "runtime_session_id": None},
    ],
)
def test_consent_evidence_requires_tier_disclosure_and_customer_turn(evidence):
    from services.proposal_evidence import consent_evidence_ref

    with pytest.raises(ValueError):
        consent_evidence_ref(evidence, "a" * 64)
    with pytest.raises(ValueError):
        consent_evidence_ref(_consent_evidence(), "not-a-request-ref")


def test_consent_evidence_is_archived_only_through_the_allowlist():
    from services.proposal_evidence import EVIDENCE, project

    projected = project(
        {**_consent_evidence("HARD"), "inquiry_consent": {
            **_consent_evidence("HARD")["inquiry_consent"], "secret": "private"}},
        EVIDENCE,
    )
    assert projected["inquiry_consent"] == {
        "inquiry_type": "HARD",
        "disclosure_version": "hard-inquiry-disclosure.v1",
        "consent_turn_id": "turn-7",
    }
