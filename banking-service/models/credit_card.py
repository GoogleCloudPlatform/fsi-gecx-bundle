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
from sqlalchemy import (
    Column, String, Boolean, BigInteger, Integer, 
    DateTime, Numeric, ForeignKey, Index
)
from utils.database import UniversalUUID as UUID, generate_uuid
from sqlalchemy.orm import relationship
from utils.database import Base

class CreditProduct(Base):
    """
    Catalog definition for revolving credit card products.
    Enforces pricing disclosures (APR, fees) and rewards parameters.
    """
    __tablename__ = "credit_products"
    __table_args__ = {'schema': 'catalog'}

    product_code = Column(String(50), primary_key=True)  # e.g. 'PLATINUM_TRAVEL_REWARDS'
    product_name = Column(String(100), nullable=False)
    
    # Underwriting bounds
    min_credit_limit_cents = Column(BigInteger, nullable=False)
    max_credit_limit_cents = Column(BigInteger, nullable=False)
    
    # Financial rates (Regulatory Disclosures: Truth in Lending / Reg Z)
    purchase_apr = Column(Numeric(5, 4), nullable=False)  # e.g., 0.1899 (18.99%)
    cashback_rate = Column(Numeric(5, 4), nullable=False, default=0.0000)  # e.g. 0.0100 (1%)
    travel_multiplier = Column(Integer, nullable=False, default=1)  # multiplier (e.g. 3x)
    dining_multiplier = Column(Integer, nullable=False, default=1)
    annual_fee_cents = Column(BigInteger, nullable=False, default=0)
    
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))


class CreditAccount(Base):
    """
    Models the core credit account line, storing credit limits, cleared balances (debts), 
    and dynamic available credit in cents.
    """
    __tablename__ = "credit_accounts"
    __table_args__ = (
        Index("idx_credit_accounts_customer_id", "customer_id"),
        Index("idx_credit_accounts_product_code", "product_code"),
        {'schema': 'cards'},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=False)
    product_code = Column(String(50), ForeignKey("catalog.credit_products.product_code", ondelete="RESTRICT"), nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE") # 'ACTIVE', 'FROZEN', 'DELINQUENT', 'CLOSED'
    
    # Values represented in cents (BIGINT) to guarantee ledger precision
    credit_limit_cents = Column(BigInteger, nullable=False)
    cleared_balance_cents = Column(BigInteger, nullable=False, default=0)
    available_credit_cents = Column(BigInteger, nullable=False)
    
    # Billing Cycle details (Credit Accounting)
    payment_due_date = Column(DateTime, nullable=True)
    statement_close_date = Column(DateTime, nullable=True)
    last_payment_date = Column(DateTime, nullable=True)
    last_payment_amount_cents = Column(BigInteger, nullable=False, default=0)
    
    currency = Column(String(3), default="USD")
    opened_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    cards = relationship("IssuedCard", back_populates="account", cascade="all, delete-orphan")
    authorizations = relationship("TransactionAuthorization", back_populates="account")
    ledger_entries = relationship("PostedTransaction", back_populates="account")


class IssuedCard(Base):
    """
    Models the issued card instruments (virtual/physical) associated with a financial account.
    """
    __tablename__ = "issued_card"

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    account_id = Column(UUID(as_uuid=True), ForeignKey("cards.credit_accounts.id", ondelete="RESTRICT"), nullable=False)
    cardholder_name = Column(String(150), nullable=False)
    
    # PCI-DSS Token reference representing the PAN
    card_token = Column(String(255), nullable=False, unique=True)
    last_four = Column(String(4), nullable=False)
    encrypted_pin_block = Column(String(255), nullable=True)
    
    # Security lockouts
    pin_fail_count = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=False)
    
    exp_month = Column(Integer, nullable=False)
    exp_year = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE") # 'ACTIVE', 'BLOCKED', 'REPORTED_STOLEN', 'EXPIRED'
    is_virtual = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    account = relationship("CreditAccount", back_populates="cards")
    authorizations = relationship("TransactionAuthorization", back_populates="card")

    # Index for sub-millisecond card authorization validations
    __table_args__ = (
        Index("idx_issued_card_token", "card_token", unique=True),
        {'schema': 'cards'},
    )


class TransactionAuthorization(Base):
    """
    Models active authorization holds / pending transactions passed from network switches.
    """
    __tablename__ = "transaction_authorization"

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    card_id = Column(UUID(as_uuid=True), ForeignKey("cards.issued_card.id", ondelete="RESTRICT"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("cards.credit_accounts.id", ondelete="RESTRICT"), nullable=False)
    
    # ISO-8583 Multi-currency and FX tracking
    transaction_amount_cents = Column(BigInteger, nullable=False)
    transaction_currency = Column(String(3), nullable=False, default="USD")
    billing_amount_cents = Column(BigInteger, nullable=False)
    billing_currency = Column(String(3), nullable=False, default="USD")
    exchange_rate = Column(Numeric(18, 9), nullable=False, default=1.000000000)
    
    status = Column(String(20), nullable=False, default="PENDING") # 'PENDING', 'APPROVED', 'DECLINED', 'REVERSED'
    decline_reason = Column(String(50), nullable=False, default="NONE") # 'INSUFFICIENT_FUNDS', 'SUSPECTED_FRAUD', 'NONE'
    
    # Settlement keys
    auth_code = Column(String(6), nullable=False)
    retrieval_reference_number = Column(String(12), nullable=False)
    
    card_network = Column(String(30), nullable=False) # 'VISA', 'MASTERCARD'
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.merchant_master.id", ondelete="SET NULL"), nullable=True)
    merchant_store_id = Column(UUID(as_uuid=True), ForeignKey("merchants.merchant_stores.id", ondelete="SET NULL"), nullable=True)
    merchant_slug = Column(String(100), nullable=True)
    merchant_category_code = Column(String(4), nullable=False) # MCC
    merchant_name = Column(String(255), nullable=True)
    transaction_channel = Column(String(32), nullable=True)
    entry_mode = Column(String(32), nullable=True)
    merchant_country_code = Column(String(3), nullable=True)
    merchant_city = Column(String(100), nullable=True)
    merchant_region = Column(String(100), nullable=True)
    merchant_postal_code = Column(String(20), nullable=True)
    merchant_latitude = Column(Numeric(9, 6), nullable=True)
    merchant_longitude = Column(Numeric(9, 6), nullable=True)
    ip_country_code = Column(String(3), nullable=True)
    shipping_country_code = Column(String(3), nullable=True)
    is_digital_goods = Column(Boolean, nullable=False, default=False)
    fraud_risk_score = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    expires_at = Column(DateTime, nullable=False)

    # Relationships
    card = relationship("IssuedCard", back_populates="authorizations")
    account = relationship("CreditAccount", back_populates="authorizations")
    ledger_entries = relationship("PostedTransaction", back_populates="authorization")

    # Index for fast pending holds/balances computation
    __table_args__ = (
        Index("idx_auth_account_status", "account_id", "status"),
        {'schema': 'cards'},
    )


class PostedTransaction(Base):
    """
    Models the final, immutable system of record for cleared transactions and customer statement lines.
    """
    __tablename__ = "posted_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=generate_uuid)
    account_id = Column(UUID(as_uuid=True), ForeignKey("cards.credit_accounts.id", ondelete="RESTRICT"), nullable=False)
    authorization_id = Column(UUID(as_uuid=True), ForeignKey("cards.transaction_authorization.id", ondelete="SET NULL"), nullable=True)
    
    # Settlement keys
    auth_code = Column(String(6), nullable=True)
    retrieval_reference_number = Column(String(12), nullable=True)
    
    amount_cents = Column(BigInteger, nullable=False) # positive for payments/credits, negative for charges/fees
    description = Column(String(255), nullable=False)
    posted_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    # Relationships
    account = relationship("CreditAccount", back_populates="ledger_entries")
    authorization = relationship("TransactionAuthorization", back_populates="ledger_entries")

    # Index for statement and ledger query pagination
    __table_args__ = (
        Index("idx_ledger_account", "account_id"),
        Index("idx_ledger_account_posted", "account_id", "posted_at"),
        {'schema': 'cards'},
    )


AccountLedger = PostedTransaction  # Backward compatibility alias for existing imports
FinancialAccount = CreditAccount   # Backward compatibility alias for existing imports
