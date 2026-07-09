import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models.audit  # noqa: F401
import models.credit_card  # noqa: F401
import models.fraud  # noqa: F401
import models.identity  # noqa: F401
from models.credit_card import Base
from repositories.fraud import FraudAlertRepository


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
