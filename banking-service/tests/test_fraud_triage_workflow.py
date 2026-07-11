import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models.audit  # noqa: F401
import models.fraud  # noqa: F401
from models.audit import AuditOutbox
from models.credit_card import AccountLedger, Base, CreditAccount, CreditProduct, IssuedCard, TransactionAuthorization
from models.fraud import FraudCaseAction
from models.identity import User, UserSecureMessage
from repositories.fraud import FraudAlertRepository
from services.fraud_alerts import FraudAlertService


DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(name="db_session")
def fixture_db_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = testing_session_local()
    try:
        product = CreditProduct(
            product_code="CASHBACK_EVERYDAY",
            product_name="Nova Cashback Everyday",
            min_credit_limit_cents=300000,
            max_credit_limit_cents=1500000,
            purchase_apr=0.2199,
            cashback_rate=0.0150,
            travel_multiplier=1,
            dining_multiplier=1,
            annual_fee_cents=0,
        )
        user = User(
            id="88888888-8888-4888-8888-222222222222",
            auth_provider_uid="cust-test-xyz",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )
        db.add_all([product, user])
        db.flush()

        account = CreditAccount(
            id="12300000-0000-4000-8000-000000000123",
            customer_id=user.id,
            product_code=product.product_code,
            status="ACTIVE",
            credit_limit_cents=500000,
            cleared_balance_cents=3500,
            available_credit_cents=492300,
        )
        card = IssuedCard(
            id="99900000-0000-4000-8000-000000000999",
            account_id=account.id,
            cardholder_name="John Doe",
            card_token="tok_test_john_doe",
            last_four="1234",
            exp_month=11,
            exp_year=2027,
            status="ACTIVE",
            is_active=True,
        )
        posted = AccountLedger(
            id="01000000-0000-4000-8000-000000000001",
            account_id=account.id,
            amount_cents=-3500,
            description="FRAUD_POSTED_TEST",
            posted_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1),
        )
        auth = TransactionAuthorization(
            id="02000000-0000-4000-8000-000000000002",
            card_id=card.id,
            account_id=account.id,
            transaction_amount_cents=4200,
            billing_amount_cents=4200,
            status="PENDING",
            auth_code="123456",
            retrieval_reference_number="123456789012",
            card_network="VISA",
            merchant_category_code="5999",
            merchant_name="TEST FRAUD MERCHANT",
            expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
        )
        db.add_all([account, card, posted, auth])
        db.commit()
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
        message_thread_id="thread-fraud-workflow",
        suspicious_authorization_ids=["02000000-0000-4000-8000-000000000002"],
        suspicious_transactions=[
            {
                "authorization_id": "02000000-0000-4000-8000-000000000002",
                "merchant_name": "TEST FRAUD MERCHANT",
                "amount_cents": 4200,
            }
        ],
    )


@pytest.fixture(autouse=True)
def mock_firebase():
    with patch("services.messaging.messaging.send", return_value="topic-message-id"), patch(
        "services.messaging.messaging.send_each_for_multicast"
    ) as mock_multicast:
        batch = MagicMock()
        batch.success_count = 0
        batch.failure_count = 0
        mock_multicast.return_value = batch
        yield


def test_triage_fraud_case_recognized_activity_resolves_without_remediation(db_session, fraud_alert):
    result = FraudAlertService(db_session).triage_fraud_case(
        auth_provider_uid="cust-test-xyz",
        fraud_alert_id=str(fraud_alert.id),
        disputed_authorization_ids=[],
        disputed_transaction_ids=[],
        issue_replacement=False,
        idempotency_key="recognized-flow",
    )

    refreshed = FraudAlertRepository(db_session).get_alert_by_id(fraud_alert_id=fraud_alert.id)
    messages = db_session.query(UserSecureMessage).filter_by(thread_id="thread-fraud-workflow").all()
    actions = db_session.query(FraudCaseAction).filter_by(fraud_alert_id=fraud_alert.id).all()

    assert result["success"] is True
    assert result["outcome"] == "CUSTOMER_RECOGNIZED"
    assert refreshed.status == "RESOLVED_CUSTOMER_RECOGNIZED"
    assert refreshed.remediation_status == "CUSTOMER_RECOGNIZED"
    assert refreshed.provisional_credit_cents == 0
    assert result["replacement_card"] is None
    assert len(messages) == 1
    assert "recognized activity" in messages[0].message
    assert len(actions) == 1
    assert actions[0].action_type == "FRAUD_CASE_TRIAGED"


def test_scenario_customer_action_false_positive_resolves_alert(db_session, fraud_alert):
    result = FraudAlertService(db_session).execute_scenario_customer_action(
        fraud_alert_id=str(fraud_alert.id),
        outcome_label="false_positive",
        idempotency_key="scenario-false-positive",
    )

    refreshed = FraudAlertRepository(db_session).get_alert_by_id(fraud_alert_id=fraud_alert.id)

    assert result["success"] is True
    assert result["outcome"] == "CUSTOMER_RECOGNIZED"
    assert refreshed.status == "RESOLVED_CUSTOMER_RECOGNIZED"
    assert refreshed.remediation_status == "CUSTOMER_RECOGNIZED"


def test_scenario_customer_action_unresolved_leaves_alert_open(db_session, fraud_alert):
    result = FraudAlertService(db_session).execute_scenario_customer_action(
        fraud_alert_id=str(fraud_alert.id),
        outcome_label="unresolved",
        idempotency_key="scenario-unresolved",
    )

    refreshed = FraudAlertRepository(db_session).get_alert_by_id(fraud_alert_id=fraud_alert.id)

    assert result["success"] is True
    assert result["outcome"] == "UNRESOLVED"
    assert refreshed.status == "OPEN"
    assert refreshed.remediation_status == "NOT_STARTED"


def test_triage_fraud_case_disputed_activity_applies_remediation_and_message(db_session, fraud_alert):
    result = FraudAlertService(db_session).triage_fraud_case(
        auth_provider_uid="cust-test-xyz",
        fraud_alert_id=str(fraud_alert.id),
        disputed_authorization_ids=["02000000-0000-4000-8000-000000000002"],
        disputed_transaction_ids=["01000000-0000-4000-8000-000000000001"],
        issue_replacement=True,
        idempotency_key="confirmed-fraud-flow",
    )

    refreshed = FraudAlertRepository(db_session).get_alert_by_id(fraud_alert_id=fraud_alert.id)
    account = db_session.query(CreditAccount).filter_by(id="12300000-0000-4000-8000-000000000123").first()
    original_card = db_session.query(IssuedCard).filter_by(id="99900000-0000-4000-8000-000000000999").first()
    messages = db_session.query(UserSecureMessage).filter_by(thread_id="thread-fraud-workflow").all()
    triage_event = db_session.query(AuditOutbox).filter_by(event_type="FRAUD_CASE_TRIAGED").first()
    message_event = db_session.query(AuditOutbox).filter_by(event_type="FRAUD_TRIAGE_MESSAGE_SENT").first()

    assert result["success"] is True
    assert result["outcome"] == "PENDING_SPECIALIST_REVIEW"
    assert len(result["voided_authorizations"]) == 1
    assert len(result["provisional_credits"]) == 1
    assert result["replacement_card"]["new_card_id"]
    assert refreshed.status == "TRIAGED_PENDING_REVIEW"
    assert refreshed.remediation_status == "PENDING_SPECIALIST_REVIEW"
    assert refreshed.selected_disputed_authorization_ids == ["02000000-0000-4000-8000-000000000002"]
    assert refreshed.selected_disputed_transaction_ids == ["01000000-0000-4000-8000-000000000001"]
    assert refreshed.provisional_credit_cents == 3500
    assert str(refreshed.replacement_card_id) == result["replacement_card"]["new_card_id"]
    assert account.cleared_balance_cents == 0
    assert account.available_credit_cents == 500000
    assert original_card.status == "BLOCKED"
    assert len(messages) == 1
    assert "pending review" in messages[0].message
    assert "Disputed transactions:" in messages[0].message
    assert "TEST FRAUD MERCHANT: $42.00" in messages[0].message
    assert "provisional credits" in messages[0].message
    assert "pending the full fraud investigation" in messages[0].message
    assert triage_event is not None
    assert message_event is not None
    assert str(fraud_alert.id) in triage_event.payload


def test_triage_fraud_case_is_idempotent(db_session, fraud_alert):
    service = FraudAlertService(db_session)
    first = service.triage_fraud_case(
        auth_provider_uid="cust-test-xyz",
        fraud_alert_id=str(fraud_alert.id),
        disputed_authorization_ids=["02000000-0000-4000-8000-000000000002"],
        disputed_transaction_ids=["01000000-0000-4000-8000-000000000001"],
        issue_replacement=True,
        idempotency_key="retry-flow",
    )
    second = service.triage_fraud_case(
        auth_provider_uid="cust-test-xyz",
        fraud_alert_id=str(fraud_alert.id),
        disputed_authorization_ids=["02000000-0000-4000-8000-000000000002"],
        disputed_transaction_ids=["01000000-0000-4000-8000-000000000001"],
        issue_replacement=True,
        idempotency_key="retry-flow",
    )

    messages = db_session.query(UserSecureMessage).filter_by(thread_id="thread-fraud-workflow").all()
    replacements = db_session.query(IssuedCard).filter(IssuedCard.card_token.like("tok_visa_reissue_%")).all()
    workflow_actions = db_session.query(FraudCaseAction).filter_by(
        fraud_alert_id=fraud_alert.id,
        action_type="FRAUD_CASE_TRIAGED",
    ).all()

    assert first["replacement_card"]["new_card_id"] == second["replacement_card"]["new_card_id"]
    assert second["idempotent_replay"] is True
    assert len(messages) == 1
    assert len(replacements) == 1
    assert len(workflow_actions) == 1


def test_triage_idempotency_key_stays_within_schema_limit_for_many_disputes():
    disputed_authorization_ids = [
        "02000000-0000-4000-8000-000000000002",
        "02000000-0000-4000-8000-000000000003",
        "02000000-0000-4000-8000-000000000004",
        "02000000-0000-4000-8000-000000000005",
        "02000000-0000-4000-8000-000000000006",
    ]

    key = FraudAlertService._build_triage_idempotency_key(
        disputed_authorization_ids=disputed_authorization_ids,
        disputed_transaction_ids=[],
        issue_replacement=True,
        escalate=False,
    )

    assert key.startswith("triage:")
    assert len(key) <= 128


def test_triage_fraud_case_rejects_authorization_outside_alert(db_session, fraud_alert):
    with pytest.raises(ValueError, match="not part of this fraud alert"):
        FraudAlertService(db_session).triage_fraud_case(
            auth_provider_uid="cust-test-xyz",
            fraud_alert_id=str(fraud_alert.id),
            disputed_authorization_ids=["99999999-9999-4999-8999-999999999999"],
            idempotency_key="bad-auth-flow",
        )


def test_triage_fraud_case_rejects_wrong_customer(db_session, fraud_alert):
    result = FraudAlertService(db_session).triage_fraud_case(
        auth_provider_uid="other-customer",
        fraud_alert_id=str(fraud_alert.id),
        disputed_authorization_ids=[],
        idempotency_key="wrong-customer-flow",
    )

    assert result["success"] is False
    assert result["fraud_alert"] is None
