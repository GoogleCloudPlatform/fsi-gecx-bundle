import datetime
import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.audit import AuditOutbox
from models.origination import Account
from services.financial_journal import JournalEntrySpec, post_financial_transaction
from utils.database import Base


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _account(db_session, number: str) -> Account:
    account = Account(
        id=uuid.uuid4(),
        account_number=number,
        account_type="SYSTEM",
        product_name=number,
        product_code=None,
        currency="USD",
        status="ACTIVE",
    )
    db_session.add(account)
    db_session.flush()
    return account


def test_post_financial_transaction_is_balanced_and_emits_v1_contract(db_session):
    debit = _account(db_session, "TEST-DEBIT")
    credit = _account(db_session, "TEST-CREDIT")
    historical_posted_at = datetime.datetime(2020, 1, 2, tzinfo=datetime.timezone.utc)

    posting = post_financial_transaction(
        db_session,
        idempotency_key="journal-test-1",
        description="Balanced test",
        entries=(
            JournalEntrySpec(debit.id, "DEBIT", 1250),
            JournalEntrySpec(credit.id, "CREDIT", 1250),
        ),
        source_type="TEST",
        source_references={"case_id": "case-1"},
        posted_at=historical_posted_at,
    )

    event = db_session.query(AuditOutbox).filter_by(event_id=posting.event_id).one()
    payload = json.loads(event.payload)
    assert payload["schema_version"] == 1
    assert payload["transaction_id"] == str(posting.transaction.id)
    assert payload["source_references"] == {"case_id": "case-1"}
    assert sum(e["amount_cents"] for e in payload["entries"] if e["direction"] == "DEBIT") == 1250
    assert sum(e["amount_cents"] for e in payload["entries"] if e["direction"] == "CREDIT") == 1250
    assert event.created_at.year > historical_posted_at.year

    retry = post_financial_transaction(
        db_session,
        idempotency_key="journal-test-1",
        description="Balanced test retry",
        entries=(
            JournalEntrySpec(debit.id, "DEBIT", 1250),
            JournalEntrySpec(credit.id, "CREDIT", 1250),
        ),
        source_type="TEST",
    )
    assert retry.transaction.id == posting.transaction.id
    assert retry.event_id == posting.event_id
    assert db_session.query(AuditOutbox).count() == 1


def test_post_financial_transaction_rejects_idempotency_key_reuse(db_session):
    debit = _account(db_session, "REUSE-DEBIT")
    credit = _account(db_session, "REUSE-CREDIT")
    post_financial_transaction(
        db_session,
        idempotency_key="journal-reuse",
        description="Original",
        entries=(
            JournalEntrySpec(debit.id, "DEBIT", 100),
            JournalEntrySpec(credit.id, "CREDIT", 100),
        ),
        source_type="TEST",
    )

    with pytest.raises(ValueError, match="different journal entries"):
        post_financial_transaction(
            db_session,
            idempotency_key="journal-reuse",
            description="Conflicting retry",
            entries=(
                JournalEntrySpec(debit.id, "DEBIT", 200),
                JournalEntrySpec(credit.id, "CREDIT", 200),
            ),
            source_type="TEST",
        )


@pytest.mark.parametrize(
    "entries,error",
    [
        ((JournalEntrySpec(uuid.uuid4(), "DEBIT", 100),), "at least two"),
        (
            (
                JournalEntrySpec(uuid.uuid4(), "DEBIT", 100),
                JournalEntrySpec(uuid.uuid4(), "CREDIT", 99),
            ),
            "Unbalanced",
        ),
        (
            (
                JournalEntrySpec(uuid.uuid4(), "DEBIT", 0),
                JournalEntrySpec(uuid.uuid4(), "CREDIT", 0),
            ),
            "positive",
        ),
    ],
)
def test_post_financial_transaction_rejects_invalid_entries(db_session, entries, error):
    with pytest.raises(ValueError, match=error):
        post_financial_transaction(
            db_session,
            idempotency_key=str(uuid.uuid4()),
            description="Invalid",
            entries=entries,
            source_type="TEST",
        )
