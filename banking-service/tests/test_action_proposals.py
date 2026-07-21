import datetime
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models.action_proposal import ActionProposal
from models.fraud import FraudAlert
from services.action_proposals import (
    ActionProposalService,
    ProposalConflictError,
    ProposalScopeError,
    ProposalTransitionError,
    TRIAGE_FRAUD_CASE,
)


@pytest.fixture(name="db_session")
def fixture_db_session():
    engine = create_engine("sqlite:///:memory:")
    FraudAlert.__table__.create(bind=engine, checkfirst=True)
    ActionProposal.__table__.create(bind=engine, checkfirst=True)
    with Session(engine) as session:
        try:
            yield session
        finally:
            session.rollback()
    ActionProposal.__table__.drop(bind=engine)
    FraudAlert.__table__.drop(bind=engine)
    engine.dispose()


@pytest.fixture(name="fraud_alert")
def fixture_fraud_alert(db_session):
    alert = FraudAlert(
        customer_id=uuid.uuid4(),
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
                "amount_cents": 1299,
            },
            {
                "authorization_id": "auth-2",
                "transaction_id": "txn-2",
                "merchant_name": "Transit Pass",
                "amount_cents": 4500,
            },
        ],
    )
    db_session.add(alert)
    db_session.flush()
    return alert


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


def test_fraud_triage_proposal_normalizes_and_binds_immutable_payload(
    db_session, fraud_alert
):
    proposal = _propose(ActionProposalService(db_session), fraud_alert)

    assert proposal.status == "PROPOSED"
    assert proposal.contract_version == "fraud-triage.v1"
    assert proposal.action_type == TRIAGE_FRAUD_CASE
    assert proposal.action_payload == {
        "disputed_authorization_ids": ["auth-1", "auth-2"],
        "disputed_transaction_ids": [],
        "escalate": False,
        "fraud_alert_id": str(fraud_alert.id),
        "issue_replacement": True,
    }
    assert len(proposal.payload_fingerprint) == 64
    assert str(proposal.customer_id) == str(fraud_alert.customer_id)
    assert str(proposal.account_id) == str(fraud_alert.credit_account_id)
    assert proposal.reset_generation == "3:9"
    assert proposal.catalog_snapshot_id == "fraud-guidance-v7"
    assert "$12.99 at Corner Market" in proposal.customer_safe_summary
    assert "$45.00 at Transit Pass" in proposal.customer_safe_summary


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
    assert db_session.query(ActionProposal).count() == 1

    with pytest.raises(ProposalConflictError, match="different proposal"):
        _propose(
            service,
            fraud_alert,
            disputed_authorization_ids=["auth-1"],
        )


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
