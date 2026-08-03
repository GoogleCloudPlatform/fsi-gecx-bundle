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
from sqlalchemy.orm import Session, sessionmaker

from models.action_proposal import (
    ActionProposal,
    CONFIRMATION_POLICIES,
    PROPOSAL_STATUSES,
)
from models.fraud import FraudAlert
from models.identity import User
from services.action_proposal_context import ProposalRuntimeContext
from services.action_proposals import (
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

FROZEN_PROPOSAL_COLUMNS = {
    "id",
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


@pytest.fixture(name="db_session")
def fixture_db_session():
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(bind=engine, checkfirst=True)
    FraudAlert.__table__.create(bind=engine, checkfirst=True)
    ActionProposal.__table__.create(bind=engine, checkfirst=True)
    with Session(engine) as session:
        try:
            yield session
        finally:
            session.rollback()
    ActionProposal.__table__.drop(bind=engine)
    FraudAlert.__table__.drop(bind=engine)
    User.__table__.drop(bind=engine)
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
    expires_at: datetime.datetime | None = None,
) -> ActionProposal:
    """Create one neutral fixture through the current durable envelope seam."""
    return service._create(
        contract_version=contract_version,
        action_type=action_type,
        customer_id=alert.customer_id,
        account_id=alert.credit_account_id,
        support_session_id="support-session-contract",
        runtime_name="ADK_GEMINI_LIVE",
        runtime_session_id="runtime-session-contract",
        originating_customer_turn_id=f"customer-origin-{suffix}",
        reset_generation="3:9",
        confirmation_policy="EXPLICIT_VERBAL",
        action_payload={"fixture": suffix},
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
    with pytest.raises(ProposalTransitionError, match="expired"):
        service.mark_presented(
            expired.id,
            assistant_turn_id="assistant-too-late",
            now=expires_at + datetime.timedelta(seconds=1),
        )
    assert expired.status == "EXPIRED"
    assert expired.invalidation_reason == "PROPOSAL_EXPIRED"

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
    with pytest.raises(ProposalScopeError, match="session reset"):
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


def test_concurrent_proposal_creation_returns_the_same_idempotent_row(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'proposal-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    User.__table__.create(bind=engine, checkfirst=True)
    FraudAlert.__table__.create(bind=engine, checkfirst=True)
    ActionProposal.__table__.create(bind=engine, checkfirst=True)
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
        "services.action_proposals.CreditCardRepository",
        lambda _db: repository,
    )
    return account, card


def test_card_reissue_uses_generic_proposal_commit_protocol(
    db_session, fraud_alert, monkeypatch
):
    _, card = _mock_card_repository(monkeypatch, fraud_alert)
    monkeypatch.setattr(
        "services.action_proposals.record_audit_event",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "services.action_proposals.issue_replacement_card",
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
    monkeypatch.setattr(
        "services.action_proposals.record_audit_event",
        lambda *_args, **_kwargs: None,
    )
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
        "services.action_proposals.queue_wallet_provisioning", fake_queue
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
