import datetime
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models.audit  # noqa: F401
import models.credit_card  # noqa: F401
import models.fraud  # noqa: F401
import models.identity  # noqa: F401
from models.credit_card import Base
from repositories.fraud import FraudAlertRepository, FraudDecisionRepository
from repositories.synthetic_schedule import SyntheticScheduledEventRepository


DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(name="db_session")
def fixture_db_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = testing_session_local()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def fraud_alert(db_session):
    return FraudAlertRepository(db_session).create_alert(
        customer_id="88888888-8888-4888-8888-222222222222",
        auth_provider_uid="cust-test-xyz",
        credit_account_id="12300000-0000-4000-8000-000000000123",
        card_id="99900000-0000-4000-8000-000000000999",
        card_last_four="1234",
        message_thread_id="thread-fraud-repo-1",
        suspicious_authorization_ids=["auth-1", "auth-2"],
        suspicious_transactions=[
            {"authorization_id": "auth-1", "merchant_name": "TEST GIFT CARD", "amount_cents": 25000},
            {"authorization_id": "auth-2", "merchant_name": "TEST TRAVEL", "amount_cents": 50000},
        ],
    )


def test_mark_triaged_persists_operational_fraud_state(db_session, fraud_alert):
    repo = FraudAlertRepository(db_session)

    triaged = repo.mark_triaged(
        fraud_alert_id=fraud_alert.id,
        remediation_status="PENDING_SPECIALIST_REVIEW",
        triage_summary="Customer disputed one pending authorization.",
        selected_disputed_authorization_ids=["auth-1"],
        selected_disputed_transaction_ids=[],
        provisional_credit_cents=25000,
        replacement_card_id="11111111-1111-4111-8111-111111111111",
        triage_message_thread_id="thread-fraud-repo-1",
        triage_message_id="message-1",
    )

    assert triaged is not None
    assert triaged.remediation_status == "PENDING_SPECIALIST_REVIEW"
    assert triaged.triaged_at is not None
    assert triaged.triage_summary == "Customer disputed one pending authorization."
    assert triaged.selected_disputed_authorization_ids == ["auth-1"]
    assert triaged.selected_disputed_transaction_ids == []
    assert triaged.provisional_credit_cents == 25000
    assert str(triaged.replacement_card_id) == "11111111-1111-4111-8111-111111111111"
    assert triaged.triage_message_thread_id == "thread-fraud-repo-1"
    assert triaged.triage_message_id == "message-1"


def test_create_case_action_is_idempotent_for_same_alert_and_key(db_session, fraud_alert):
    repo = FraudAlertRepository(db_session)

    first = repo.create_case_action(
        fraud_alert_id=fraud_alert.id,
        action_type="FRAUD_CASE_TRIAGED",
        status="SUCCEEDED",
        idempotency_key="voice-session-1:triage",
        request_payload={"selected_authorization_ids": ["auth-1"]},
        result_payload={"remediation_status": "PENDING_SPECIALIST_REVIEW"},
        completed_at=datetime.datetime.now(datetime.timezone.utc),
    )
    second = repo.create_case_action(
        fraud_alert_id=fraud_alert.id,
        action_type="FRAUD_CASE_TRIAGED",
        status="PENDING",
        idempotency_key="voice-session-1:triage",
        request_payload={"selected_authorization_ids": ["auth-2"]},
    )

    actions = repo.list_case_actions(fraud_alert_id=fraud_alert.id)
    assert second.id == first.id
    assert len(actions) == 1
    assert actions[0].status == "SUCCEEDED"
    assert actions[0].request_payload == {"selected_authorization_ids": ["auth-1"]}


def test_complete_case_action_records_result_and_completion_time(db_session, fraud_alert):
    repo = FraudAlertRepository(db_session)
    action = repo.create_case_action(
        fraud_alert_id=fraud_alert.id,
        action_type="FRAUD_PROVISIONAL_CREDIT_APPLIED",
        idempotency_key="credit-auth-1",
        request_payload={"authorization_id": "auth-1"},
    )

    completed = repo.complete_case_action(
        action_id=action.id,
        status="SUCCEEDED",
        result_payload={"credit_cents": 25000},
    )

    assert completed is not None
    assert completed.status == "SUCCEEDED"
    assert completed.result_payload == {"credit_cents": 25000}
    assert completed.completed_at is not None


def test_synthetic_scheduled_event_repository_idempotent_lifecycle(db_session):
    repo = SyntheticScheduledEventRepository(db_session)
    scheduled_for = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        minutes=5
    )

    first = repo.create_event(
        schedule_id="schedule-1",
        scenario_id="scenario-1",
        execution_id="execution-1",
        event_id="auth-1",
        event_type="authorization",
        persona_id="persona-1",
        scheduled_for=scheduled_for,
        idempotency_key="schedule-1:auth-1",
        payload={"amount_cents": 4200},
    )
    second = repo.create_event(
        schedule_id="schedule-1",
        event_id="auth-1-retry",
        event_type="authorization",
        scheduled_for=scheduled_for,
        idempotency_key="schedule-1:auth-1",
        payload={"amount_cents": 9999},
    )

    assert second.id == first.id
    assert second.event_id == "auth-1"

    dispatching = repo.mark_dispatching(first.id)
    assert dispatching.status == "DISPATCHING"
    assert dispatching.attempts == 1

    completed = repo.mark_succeeded(
        event_record_id=first.id,
        result_payload={"authorization_id": "auth-result-1"},
    )
    assert completed.status == "SUCCEEDED"
    assert completed.result_payload == {"authorization_id": "auth-result-1"}

    completed_context = repo.list_completed_before(
        schedule_id="schedule-1", persona_id="persona-1"
    )
    assert [event.id for event in completed_context] == [first.id]


def test_synthetic_scheduled_event_repository_cancels_future_events(db_session):
    repo = SyntheticScheduledEventRepository(db_session)
    now = datetime.datetime.now(datetime.timezone.utc)
    repo.create_event(
        schedule_id="schedule-cancel",
        event_id="future-auth",
        event_type="authorization",
        scheduled_for=now + datetime.timedelta(minutes=5),
        idempotency_key="schedule-cancel:future-auth",
    )
    repo.create_event(
        schedule_id="schedule-cancel",
        event_id="past-auth",
        event_type="authorization",
        scheduled_for=now - datetime.timedelta(minutes=5),
        idempotency_key="schedule-cancel:past-auth",
    )

    canceled = repo.cancel_future_events(schedule_id="schedule-cancel")
    events = repo.list_events(schedule_id="schedule-cancel")

    assert canceled == 1
    assert {event.event_id: event.status for event in events} == {
        "past-auth": "SCHEDULED",
        "future-auth": "CANCELED",
    }


def test_record_model_decision_is_idempotent_for_authorization(db_session):
    repo = FraudDecisionRepository(db_session)
    authorization_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    account_id = uuid.uuid4()
    card_id = uuid.uuid4()
    feature_snapshot = {
        "merchant_name": "RAZER GOLD GIFT CARD",
        "merchant_category_code": "5947",
        "transaction_channel": "ECOMMERCE",
        "merchant_country_code": "USA",
        "merchant_city": "San Francisco",
        "merchant_region": "CA",
        "recent_auth_count_10m": 3,
    }

    first = repo.record_model_decision(
        authorization_id=authorization_id,
        customer_id=customer_id,
        credit_account_id=account_id,
        card_id=card_id,
        score=91,
        threshold=20,
        decision="FLAGGED",
        reason_codes=["GIFT_CARD_OR_DIGITAL_GOODS"],
        feature_snapshot=feature_snapshot,
        model_version="local-deterministic-v1",
    )
    second = repo.record_model_decision(
        authorization_id=authorization_id,
        customer_id=customer_id,
        credit_account_id=account_id,
        card_id=card_id,
        score=3,
        threshold=20,
        decision="APPROVED",
        reason_codes=["BASELINE_LOW_RISK"],
        feature_snapshot={},
        model_version="local-deterministic-v1",
    )

    assert second.id == first.id
    assert second.score == 91
    assert second.reason_codes == ["GIFT_CARD_OR_DIGITAL_GOODS"]
    assert second.feature_snapshot["recent_auth_count_10m"] == 3
    assert second.transaction_channel == "ECOMMERCE"


def test_append_suspicious_authorization_deduplicates_alert_items(db_session, fraud_alert):
    repo = FraudAlertRepository(db_session)
    transaction = {
        "authorization_id": "auth-3",
        "merchant_name": "MODEL DETECTED MERCHANT",
        "amount_cents": 9900,
        "fraud_score": 82,
    }

    first = repo.append_suspicious_authorization(
        fraud_alert_id=fraud_alert.id,
        authorization_id="auth-3",
        suspicious_transaction=transaction,
    )
    second = repo.append_suspicious_authorization(
        fraud_alert_id=fraud_alert.id,
        authorization_id="auth-3",
        suspicious_transaction=transaction,
    )

    assert first.id == second.id
    assert second.suspicious_authorization_ids.count("auth-3") == 1
    assert len([txn for txn in second.suspicious_transactions if txn.get("authorization_id") == "auth-3"]) == 1
