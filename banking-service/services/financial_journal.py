# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Canonical balanced financial journal posting primitives."""

from __future__ import annotations

import datetime
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy.orm import Session

from models.audit import AuditOutbox
from models.credit_card import CreditAccount
from models.origination import Account, AccountLedgerEntry, Transaction
from utils.audit import record_audit_event


FINANCIAL_EVENT_TYPE = "FINANCIAL_TRANSACTION_POSTED"
FINANCIAL_EVENT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class JournalEntrySpec:
    account_id: uuid.UUID | str
    direction: str
    amount_cents: int


@dataclass(frozen=True)
class JournalPosting:
    transaction: Transaction
    entries: tuple[AccountLedgerEntry, ...]
    event_id: str


def ensure_system_journal_account(db: Session, account_number: str, description: str) -> Account:
    """Returns a durable clearing account used as a balancing counterparty."""
    account = db.query(Account).filter(Account.account_number == account_number).one_or_none()
    if account:
        return account
    account = Account(
        user_id=None,
        account_number=account_number,
        account_type="SYSTEM",
        product_name=description,
        product_code=None,
        cleared_balance_cents=0,
        available_credit_cents=0,
        credit_limit_cents=0,
        currency="USD",
        status="ACTIVE",
    )
    db.add(account)
    db.flush()
    return account


def ensure_credit_journal_account(db: Session, credit_account: CreditAccount) -> Account:
    """Returns the canonical receivable journal account for a card account."""
    account = (
        db.query(Account)
        .filter(Account.credit_account_id == credit_account.id)
        .one_or_none()
    )
    if account:
        account.status = credit_account.status
        account.cleared_balance_cents = credit_account.cleared_balance_cents
        account.available_credit_cents = credit_account.available_credit_cents
        account.credit_limit_cents = credit_account.credit_limit_cents
        return account

    account = Account(
        user_id=credit_account.customer_id,
        account_number=f"CARD-{credit_account.id}",
        account_type="CREDIT_CARD",
        product_name=f"Card receivable ({credit_account.product_code})",
        product_code=None,
        credit_account_id=credit_account.id,
        credit_limit_cents=credit_account.credit_limit_cents,
        cleared_balance_cents=credit_account.cleared_balance_cents,
        available_credit_cents=credit_account.available_credit_cents,
        currency=credit_account.currency or "USD",
        status=credit_account.status,
    )
    db.add(account)
    db.flush()
    return account


def post_financial_transaction(
    db: Session,
    *,
    idempotency_key: str,
    description: str,
    entries: Iterable[JournalEntrySpec],
    source_type: str,
    currency: str = "USD",
    source_references: dict[str, Any] | None = None,
    user_id: uuid.UUID | str | None = None,
    posted_at: datetime.datetime | None = None,
) -> JournalPosting:
    """Appends a balanced transaction and versioned event without committing."""
    normalized: list[JournalEntrySpec] = []
    for spec in entries:
        direction = str(spec.direction).upper()
        amount = int(spec.amount_cents)
        if direction not in {"DEBIT", "CREDIT"}:
            raise ValueError(f"Invalid journal direction: {spec.direction!r}")
        if amount <= 0:
            raise ValueError("Journal amounts must be positive; direction carries the sign.")
        normalized.append(JournalEntrySpec(spec.account_id, direction, amount))

    if len(normalized) < 2:
        raise ValueError("A financial transaction requires at least two journal entries.")
    debit_total = sum(item.amount_cents for item in normalized if item.direction == "DEBIT")
    credit_total = sum(item.amount_cents for item in normalized if item.direction == "CREDIT")
    if debit_total != credit_total:
        raise ValueError(
            f"Unbalanced {currency} transaction: debits={debit_total}, credits={credit_total}."
        )

    existing = db.query(Transaction).filter(Transaction.idempotency_key == idempotency_key).one_or_none()
    if existing:
        existing_entries = tuple(
            db.query(AccountLedgerEntry)
            .filter(AccountLedgerEntry.transaction_id == existing.id)
            .order_by(AccountLedgerEntry.entry_id)
            .all()
        )
        requested_signature = Counter(
            (str(item.account_id), item.direction, item.amount_cents) for item in normalized
        )
        existing_signature = Counter(
            (str(item.account_id), item.entry_type, item.amount_cents)
            for item in existing_entries
        )
        if requested_signature != existing_signature:
            raise ValueError(
                "Financial transaction idempotency key was reused with different "
                f"journal entries: {idempotency_key}"
            )
        event = (
            db.query(AuditOutbox)
            .filter(
                AuditOutbox.event_type == FINANCIAL_EVENT_TYPE,
                AuditOutbox.payload.like(f'%"transaction_id":"{existing.id}"%'),
            )
            .one_or_none()
        )
        return JournalPosting(
            transaction=existing,
            entries=existing_entries,
            event_id=event.event_id if event else f"existing:{existing.id}",
        )

    timestamp = posted_at or datetime.datetime.now(datetime.timezone.utc)
    transaction = Transaction(
        id=uuid.uuid4(),
        idempotency_key=idempotency_key,
        user_id=user_id,
        status="COMPLETED",
        description=description,
    )
    journal_entries = tuple(
        AccountLedgerEntry(
            entry_id=uuid.uuid4(),
            transaction_id=transaction.id,
            account_id=spec.account_id,
            amount_cents=spec.amount_cents,
            entry_type=spec.direction,
            posted_at=timestamp,
        )
        for spec in normalized
    )
    db.add(transaction)
    db.add_all(journal_entries)
    db.flush()

    event_id = str(uuid.uuid4())
    payload = {
        "event_id": event_id,
        "schema_version": FINANCIAL_EVENT_SCHEMA_VERSION,
        "transaction_id": str(transaction.id),
        "event_time": timestamp.isoformat(),
        "posted_at": timestamp.isoformat(),
        "currency": currency.upper(),
        "source_type": source_type,
        "source_references": source_references or {},
        "description": description,
        "entries": [
            {
                "entry_id": str(entry.entry_id),
                "account_id": str(entry.account_id),
                "direction": entry.entry_type,
                "amount_cents": entry.amount_cents,
            }
            for entry in journal_entries
        ],
    }
    record_audit_event(
        db,
        FINANCIAL_EVENT_TYPE,
        payload,
        event_id=event_id,
        schema_version=FINANCIAL_EVENT_SCHEMA_VERSION,
    )
    return JournalPosting(transaction=transaction, entries=journal_entries, event_id=event_id)
