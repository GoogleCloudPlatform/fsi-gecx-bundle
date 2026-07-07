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
from typing import Optional, List, Any
from sqlalchemy.orm import Session
from models.credit_card import FinancialAccount, IssuedCard, AccountLedger, TransactionAuthorization

from models.identity import User
import uuid

class CreditCardRepository:
    """
    Repository encapsulating persistence logic and database access for Financial Accounts, 
    Issued Cards, Ledger Entries, and Transaction Authorizations.
    """
    def __init__(self, db: Session):
        self.db = db

    def _resolve_user_id(self, customer_id: str) -> str:
        """Resolves an auth_provider_uid or raw string to a database user UUID."""
        # If it's already a valid UUID format, check if we can query it directly
        try:
            uuid_val = uuid.UUID(customer_id)
            user_exists = self.db.query(User).filter(User.id == uuid_val).first()
            if user_exists:
                return str(uuid_val)
        except ValueError:
            pass

        # Otherwise, look up by auth_provider_uid
        user = self.db.query(User).filter(User.auth_provider_uid == customer_id).first()
        if user:
            return str(user.id)
        # Return a dummy valid UUID instead of raw string to prevent SQLAlchemy StatementError coercion failures
        return "00000000-0000-0000-0000-000000000000"

    # --- Financial Account Queries ---
    def get_account_by_id(self, account_id: str, lock: bool = False) -> Optional[FinancialAccount]:
        """Retrieves a Financial Account by its unique ID. Supports row locking."""
        query = self.db.query(FinancialAccount).filter(FinancialAccount.id == account_id)
        if lock:
            return query.with_for_update().one_or_none()
        return query.first()

    def get_account_by_customer(self, customer_id: str) -> Optional[FinancialAccount]:
        """Retrieves a Financial Account matching the specified customer ID."""
        resolved_uid = self._resolve_user_id(customer_id)
        return self.db.query(FinancialAccount).filter(FinancialAccount.customer_id == resolved_uid).first()

    def save_account(self, account: FinancialAccount) -> FinancialAccount:
        """Saves a Financial Account instance to the session."""
        self.db.add(account)
        self.db.flush()
        return account

    # --- Issued Card Queries ---
    def get_card_by_id(self, card_id: str) -> Optional[IssuedCard]:
        """Retrieves an Issued Card by its primary card ID."""
        return self.db.query(IssuedCard).filter(IssuedCard.id == card_id).first()

    def get_card_by_token(self, card_token: str) -> Optional[IssuedCard]:
        """Retrieves an Issued Card by its unique token reference."""
        return self.db.query(IssuedCard).filter(IssuedCard.card_token == card_token).first()

    def list_cards_by_account(self, account_id: str) -> List[IssuedCard]:
        """Retrieves all Issued Cards registered under the specified Financial Account."""
        return self.db.query(IssuedCard).filter(IssuedCard.account_id == account_id).all()

    def get_card_by_customer_secured(self, card_id: str, customer_id: str) -> Optional[IssuedCard]:
        """Secured retrieval verifying the card belongs to the active customer context."""
        resolved_uid = self._resolve_user_id(customer_id)
        return self.db.query(IssuedCard).join(FinancialAccount).filter(
            IssuedCard.id == card_id,
            FinancialAccount.customer_id == resolved_uid
        ).first()

    def get_card_by_token_secured(self, card_token: str, customer_id: str) -> Optional[IssuedCard]:
        """Secured token retrieval verifying the card belongs to the active customer context."""
        resolved_uid = self._resolve_user_id(customer_id)
        return self.db.query(IssuedCard).join(FinancialAccount).filter(
            IssuedCard.card_token == card_token,
            FinancialAccount.customer_id == resolved_uid
        ).first()

    def save_card(self, card: IssuedCard) -> IssuedCard:
        """Saves an Issued Card instance to the session."""
        self.db.add(card)
        self.db.flush()
        return card

    # --- Ledger Entries Queries ---
    def list_ledger_entries(self, account_id: str, limit: Optional[int] = None) -> List[AccountLedger]:
        """Retrieves transactions ledger entries for an account, sorted by date descending."""
        query = self.db.query(AccountLedger).filter(AccountLedger.account_id == account_id).order_by(AccountLedger.posted_at.desc())
        if limit:
            query = query.limit(limit)
        return query.all()

    def list_authorizations(self, account_id: str, status: Optional[str] = "PENDING") -> List[TransactionAuthorization]:
        """Retrieves authorization holds for an account."""
        query = self.db.query(TransactionAuthorization).filter(TransactionAuthorization.account_id == account_id)
        if status:
            query = query.filter(TransactionAuthorization.status == status)
        return query.order_by(TransactionAuthorization.created_at.desc()).all()

    def get_ledger_entry_by_id(self, entry_id: str) -> Optional[AccountLedger]:
        """Retrieves a single ledger entry transaction by its unique ID."""
        return self.db.query(AccountLedger).filter(AccountLedger.id == entry_id).first()

    def save_ledger(self, entry: AccountLedger) -> AccountLedger:
        """Saves an Account Ledger transaction entry to the session."""
        self.db.add(entry)
        self.db.flush()
        return entry

    def get_reversal_entry(self, account_id: str, original_tx_id: str) -> Optional[AccountLedger]:
        """Checks if a reversal transaction already exists for the specified transaction ID."""
        reversal_description_old = f"FEE_REVERSAL_REF_{original_tx_id}"
        reversal_description_new = f"REVERSAL_REF_{original_tx_id}"
        return self.db.query(AccountLedger).filter(
            AccountLedger.account_id == account_id,
            AccountLedger.authorization_id.is_(None),
            AccountLedger.description.in_([reversal_description_old, reversal_description_new])
        ).first()

    def get_annual_reversal_entry(self, account_id: str, year_start: datetime.datetime) -> Optional[AccountLedger]:
        """Retrieves any fee reversal entry posted on or after year_start for policy limiting checks."""
        return self.db.query(AccountLedger).filter(
            AccountLedger.account_id == account_id,
            AccountLedger.posted_at >= year_start,
            AccountLedger.description.like("FEE_REVERSAL_REF_%") | AccountLedger.description.like("REVERSAL_REF_%")
        ).first()

    # --- Transaction Authorization Queries ---
    def get_authorization_by_id(self, auth_id: str) -> Optional[TransactionAuthorization]:
        """Retrieves a transaction authorization by its ID."""
        return self.db.query(TransactionAuthorization).filter(TransactionAuthorization.id == auth_id).first()

    def save_authorization(self, auth: TransactionAuthorization) -> TransactionAuthorization:
        """Saves a Transaction Authorization record to the session."""
        self.db.add(auth)
        self.db.flush()
        return auth

    def list_pending_authorizations(self, account_id: str) -> List[TransactionAuthorization]:
        """Retrieves active pending authorization holds for an account."""
        return self.db.query(TransactionAuthorization).filter(
            TransactionAuthorization.account_id == account_id,
            TransactionAuthorization.status == "PENDING"
        ).order_by(TransactionAuthorization.created_at.desc()).all()

    def get_all_accounts(self) -> List[FinancialAccount]:
        """Retrieves all Financial Accounts registered in the database."""
        return self.db.query(FinancialAccount).all()

    def get_pending_auth_total(self, account_id: str) -> int:
        """Calculates the sum of all pending authorization holds for an account."""
        from sqlalchemy import func
        res = self.db.query(func.sum(TransactionAuthorization.transaction_amount_cents)).filter(
            TransactionAuthorization.account_id == account_id,
            TransactionAuthorization.status == "PENDING"
        ).scalar()
        return int(res or 0)

    def get_authorization_by_rrn(self, rrn: str, status: Optional[str] = None) -> Optional[TransactionAuthorization]:
        """Retrieves a transaction authorization by its retrieval reference number and optional status."""
        query = self.db.query(TransactionAuthorization).filter(TransactionAuthorization.retrieval_reference_number == rrn)
        if status:
            query = query.filter(TransactionAuthorization.status == status)
        return query.first()

    def get_credit_product(self, product_code: str) -> Optional[Any]:
        """Retrieves a CreditProduct catalog entity by its product code."""
        from models.credit_card import CreditProduct
        return self.db.query(CreditProduct).filter(CreditProduct.product_code == product_code).first()

    def list_active_cards_for_simulation(self) -> List[tuple[IssuedCard, FinancialAccount]]:
        """Returns active cards joined with their backing credit accounts for simulation tooling."""
        return (
            self.db.query(IssuedCard, FinancialAccount)
            .join(FinancialAccount, IssuedCard.account_id == FinancialAccount.id)
            .filter(IssuedCard.status == "ACTIVE", IssuedCard.is_active)
            .all()
        )

    def get_active_card_for_customer(self, customer_id: str) -> tuple[IssuedCard, FinancialAccount] | None:
        """Returns one active card for the specified customer UUID or auth-provider UID."""
        resolved_uid = self._resolve_user_id(customer_id)
        return (
            self.db.query(IssuedCard, FinancialAccount)
            .join(FinancialAccount, IssuedCard.account_id == FinancialAccount.id)
            .filter(
                FinancialAccount.customer_id == resolved_uid,
                IssuedCard.status == "ACTIVE",
                IssuedCard.is_active,
            )
            .first()
        )
