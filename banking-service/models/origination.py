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

import uuid
import datetime
from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey, Integer, Index, Text
from utils.database import UniversalUUID as UUID, generate_uuid
from sqlalchemy.orm import relationship
from utils.database import Base


class Account(Base):
    """Universal account record supporting CREDIT_CARD, CHECKING, SAVINGS, and SYSTEM clearing accounts."""
    __tablename__ = "accounts"
    __table_args__ = (
        Index("idx_accounts_user_id", "user_id"),
        Index("idx_accounts_number", "account_number"),
        {'schema': 'ledger'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=True)  # Nullable for SYSTEM accounts
    account_number = Column(String(50), unique=True, nullable=False)
    account_type = Column(String(30), nullable=False)  # 'CREDIT_CARD', 'CHECKING', 'SAVINGS', 'SYSTEM'
    product_name = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE")
    credit_limit_cents = Column(BigInteger, nullable=False, default=0)
    cleared_balance_cents = Column(BigInteger, nullable=False, default=0)
    available_credit_cents = Column(BigInteger, nullable=False, default=0)
    currency = Column(String(3), default="USD")
    opened_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    ledger_entries = relationship("AccountLedgerEntry", back_populates="account")


class Application(Base):
    """Base polymorphic origination application."""
    __tablename__ = "applications"
    __table_args__ = (
        Index("idx_applications_user_id", "user_id"),
        Index("idx_applications_app_id", "application_id"),
        {'schema': 'ledger'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    application_id = Column(String(128), unique=True, nullable=False)  # External reference UUID string
    user_id = Column(UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=False)
    product_category = Column(String(50), nullable=False)  # 'MORTGAGE', 'CREDIT_CARD', 'DEPOSIT'
    status = Column(String(50), nullable=False, default="STARTED")
    requested_amount_cents = Column(BigInteger, nullable=True)
    started_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    last_updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    user = relationship("User", backref="applications")
    artifacts = relationship("ApplicationArtifact", back_populates="application", cascade="all, delete")
    mortgage_detail = relationship("MortgageApplication", back_populates="application", uselist=False, cascade="all, delete")
    credit_card_detail = relationship("CreditCardApplication", back_populates="application", uselist=False, cascade="all, delete")
    deposit_detail = relationship("DepositApplication", back_populates="application", uselist=False, cascade="all, delete")


class MortgageApplication(Base):
    """1-to-1 extension table for mortgage pre-approvals."""
    __tablename__ = "mortgage_applications"
    __table_args__ = {'schema': 'ledger'}

    application_id = Column(UUID(as_uuid=True), ForeignKey("ledger.applications.id", ondelete="CASCADE"), primary_key=True)
    property_address = Column(String(255), nullable=True)
    estimated_value_cents = Column(BigInteger, nullable=True)
    loan_term_months = Column(Integer, nullable=True)
    down_payment_cents = Column(BigInteger, nullable=True)

    application = relationship("Application", back_populates="mortgage_detail")


class CreditCardApplication(Base):
    """1-to-1 extension table for credit card originations."""
    __tablename__ = "credit_card_applications"
    __table_args__ = {'schema': 'ledger'}

    application_id = Column(UUID(as_uuid=True), ForeignKey("ledger.applications.id", ondelete="CASCADE"), primary_key=True)
    requested_limit_cents = Column(BigInteger, nullable=True)
    card_product_id = Column(String(50), nullable=True)

    application = relationship("Application", back_populates="credit_card_detail")


class DepositApplication(Base):
    """1-to-1 extension table for checking/savings deposit originations."""
    __tablename__ = "deposit_applications"
    __table_args__ = {'schema': 'ledger'}

    application_id = Column(UUID(as_uuid=True), ForeignKey("ledger.applications.id", ondelete="CASCADE"), primary_key=True)
    deposit_product_name = Column(String(100), nullable=True)
    initial_deposit_cents = Column(BigInteger, nullable=True)

    application = relationship("Application", back_populates="deposit_detail")


class ApplicationArtifact(Base):
    """Document verification artifacts uploaded during loan application workflows."""
    __tablename__ = "application_artifacts"
    __table_args__ = (
        Index("idx_artifacts_application_id", "application_id"),
        Index("idx_artifacts_customer_id", "customer_id"),
        {'schema': 'ledger'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    artifact_id = Column(String(128), unique=True, nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("ledger.applications.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=False)
    claimed_artifact_type = Column(String(100), nullable=True)
    gcs_uri = Column(String(500), nullable=False)
    status = Column(String(50), default="PENDING_CLASSIFICATION")
    version_id = Column(String(128), nullable=True)
    uploaded_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    application = relationship("Application", back_populates="artifacts")
    customer = relationship("User")


class Transaction(Base):
    """Parent financial transaction header supporting idempotency tracking."""
    __tablename__ = "transactions"
    __table_args__ = (
        Index("idx_transactions_idempotency_key", "idempotency_key"),
        Index("idx_transactions_user_id", "user_id"),
        Index("idx_transactions_user_idemp", "user_id", "idempotency_key", unique=True),
        {'schema': 'ledger'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    idempotency_key = Column(String(128), unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")
    description = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=True)
    response_payload = Column(Text, nullable=True)
    response_status = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    ledger_splits = relationship("AccountLedgerEntry", back_populates="transaction")


class AccountLedgerEntry(Base):
    """Immutable double-entry journal splits table."""
    __tablename__ = "account_ledger"
    __table_args__ = (
        Index("idx_ledger_account_id", "account_id"),
        Index("idx_ledger_transaction_id", "transaction_id"),
        {'schema': 'ledger'},
    )

    entry_id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("ledger.transactions.id", ondelete="RESTRICT"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("ledger.accounts.id", ondelete="RESTRICT"), nullable=False)
    amount_cents = Column(BigInteger, nullable=False)
    entry_type = Column(String(10), nullable=False)  # 'DEBIT', 'CREDIT'
    posted_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    transaction = relationship("Transaction", back_populates="ledger_splits")
    account = relationship("Account", back_populates="ledger_entries")
