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
import random
import datetime
import logging
from typing import Dict, Any
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.identity import User
from models.origination import Account, Application, DepositApplication, Transaction, AccountLedgerEntry
from models.authentication import ValidatedToken
from services.profile import ProfileService

logger = logging.getLogger(__name__)


class DepositAccountCreateRequest(BaseModel):
    account_type: str = Field(..., description="CHECKING or SAVINGS")
    product_name: str = Field(..., description="Name of the banking product")
    member_type: str = Field("current", description="current or new")
    initial_deposit_cents: int = Field(0, ge=0, description="Initial funding deposit in cents")


class AccountsService:
    def __init__(self, db: Session):
        self.db = db

    def create_deposit_account(
        self,
        request: DepositAccountCreateRequest,
        token: ValidatedToken,
        idempotency_key: str | None = None
    ) -> Dict[str, Any]:
        """
        Creates a new Checking or Savings deposit account.
        If initial funding is provided, posts a balanced double-entry journal transaction
        against the SYSTEM_EXTERNAL_FUNDING counterparty account.
        """
        acc_type = request.account_type.upper()
        if acc_type not in ("CHECKING", "SAVINGS"):
            raise HTTPException(status_code=400, detail="Invalid account_type. Must be CHECKING or SAVINGS.")

        # Resolve internal User entity
        user = self.db.query(User).filter(User.auth_provider_uid == token.user_id).first()
        if not user:
            ProfileService(self.db).get_or_provision_profile(token)
            user = self.db.query(User).filter(User.auth_provider_uid == token.user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User profile could not be resolved.")

        # Generate unique account number
        prefix = "CHK" if acc_type == "CHECKING" else "SAV"
        account_number = f"{prefix}-{random.randint(10000000, 99999999)}"
        while self.db.query(Account).filter_by(account_number=account_number).first():
            account_number = f"{prefix}-{random.randint(10000000, 99999999)}"

        # Provision customer account
        new_acc = Account(
            user_id=user.id,
            account_number=account_number,
            account_type=acc_type,
            product_name=request.product_name,
            cleared_balance_cents=request.initial_deposit_cents,
            status="ACTIVE"
        )
        self.db.add(new_acc)
        self.db.flush()

        # Log origination application record
        app = Application(
            application_id=f"APP-DEP-{uuid.uuid4().hex[:12]}",
            user_id=user.id,
            product_category="DEPOSIT",
            status="APPROVED",
            requested_amount_cents=request.initial_deposit_cents
        )
        self.db.add(app)
        self.db.flush()

        if app.deposit_detail:
            app.deposit_detail.deposit_product_name = request.product_name
            app.deposit_detail.initial_deposit_cents = request.initial_deposit_cents
        else:
            dep_app = DepositApplication(
                application_id=app.id,
                deposit_product_name=request.product_name,
                initial_deposit_cents=request.initial_deposit_cents
            )
            self.db.add(dep_app)
        self.db.flush()

        # If initial funding provided, post double-entry journal against clearing account
        if request.initial_deposit_cents > 0:
            sys_acc = self.db.query(Account).filter_by(account_number="SYSTEM_EXTERNAL_FUNDING", account_type="SYSTEM").first()
            if not sys_acc:
                sys_acc = Account(
                    user_id=None,
                    account_number="SYSTEM_EXTERNAL_FUNDING",
                    account_type="SYSTEM",
                    product_name="System Clearing Counterparty",
                    cleared_balance_cents=0
                )
                self.db.add(sys_acc)
                self.db.flush()

            tx = Transaction(
                idempotency_key=idempotency_key or f"IDEMP-DEP-{uuid.uuid4().hex}",
                user_id=user.id,
                status="COMPLETED",
                description=f"Initial deposit funding for {request.product_name}"
            )
            self.db.add(tx)
            self.db.flush()

            debit_split = AccountLedgerEntry(
                transaction_id=tx.id,
                account_id=new_acc.id,
                amount_cents=request.initial_deposit_cents,
                entry_type="DEBIT"
            )
            credit_split = AccountLedgerEntry(
                transaction_id=tx.id,
                account_id=sys_acc.id,
                amount_cents=request.initial_deposit_cents,
                entry_type="CREDIT"
            )
            self.db.add(debit_split)
            self.db.add(credit_split)
            sys_acc.cleared_balance_cents -= request.initial_deposit_cents

        self.db.commit()
        self.db.refresh(new_acc)

        return {
            "account_id": str(new_acc.id),
            "account_number": new_acc.account_number,
            "status": new_acc.status,
            "opened_at": new_acc.opened_at.isoformat() if new_acc.opened_at else datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

    def get_user_accounts_summary(self, token: ValidatedToken) -> Dict[str, Any]:
        """
        Retrieves checking, savings, and credit accounts for the authenticated user context.
        """
        # Resolve internal User entity
        user = self.db.query(User).filter(User.auth_provider_uid == token.user_id).first()
        if not user:
            ProfileService(self.db).get_or_provision_profile(token)
            self.db.commit()
            user = self.db.query(User).filter(User.auth_provider_uid == token.user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User profile could not be resolved.")

        # Bypass RBAC
        if hasattr(self.db.bind, "engine"):
            self.db.bind.engine._ignore_rbac = True
        else:
            self.db.bind._ignore_rbac = True

        # Fetch checking/savings accounts
        deposit_accounts = self.db.query(Account).filter(Account.user_id == user.id).all()

        # Fetch credit accounts
        from models.credit_card import CreditAccount
        credit_accounts = self.db.query(CreditAccount).filter(CreditAccount.customer_id == user.id).all()

        # Auto-provision sandbox for mock user when running locally to speed up local dev onboarding!
        from utils.env import is_running_locally
        if is_running_locally() and not deposit_accounts and not credit_accounts:
            user_email = user.email
            user_uid = user.auth_provider_uid
            user_id = user.id
            logger.info(f"Auto-provisioning local sandbox for user: {user_email}")
            from services.seeding_service import provision_user_suite
            try:
                provision_user_suite(self.db, user_email, user_uid)
                self.db.commit()
                # Fetch accounts again
                deposit_accounts = self.db.query(Account).filter(Account.user_id == user_id).all()
                credit_accounts = self.db.query(CreditAccount).filter(CreditAccount.customer_id == user_id).all()
            except Exception as e:
                logger.error(f"Failed to auto-provision local sandbox for user: {user_email}. Error: {e}")
                self.db.rollback()

        return {
            "deposit_accounts": [
                {
                    "account_id": str(acc.id),
                    "account_number": acc.account_number,
                    "account_type": acc.account_type,
                    "product_name": acc.product_name,
                    "product_code": acc.product_code,
                    "cleared_balance_cents": acc.cleared_balance_cents,
                    "routing_number": acc.routing_number,
                    "status": acc.status
                } for acc in deposit_accounts
            ],
            "credit_accounts": [
                {
                    "account_id": str(cred_acc.id),
                    "product_code": cred_acc.product_code,
                    "status": cred_acc.status,
                    "credit_limit_cents": cred_acc.credit_limit_cents,
                    "cleared_balance_cents": cred_acc.cleared_balance_cents,
                    "available_credit_cents": cred_acc.available_credit_cents,
                    "payment_due_date": cred_acc.payment_due_date.isoformat() if cred_acc.payment_due_date else None,
                    "cards": [
                        {
                            "card_id": str(card.id),
                            "cardholder_name": card.cardholder_name,
                            "last_four": card.last_four,
                            "card_token": card.card_token,
                            "status": card.status
                        } for card in cred_acc.cards
                    ]
                } for cred_acc in credit_accounts
            ]
        }

    def execute_bill_payment(
        self,
        token: ValidatedToken,
        source_account_id: str,
        credit_account_id: str,
        amount_cents: int
    ) -> Dict[str, Any]:
        """
        Executes a credit card bill payment from a checking or savings deposit account.
        Subtracts from deposit balance, reduces credit account cleared debt balance, and restores available credit.
        """
        # Resolve internal User entity
        user = self.db.query(User).filter(User.auth_provider_uid == token.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User profile not resolved.")

        # Bypass RBAC
        if hasattr(self.db.bind, "engine"):
            self.db.bind.engine._ignore_rbac = True
        else:
            self.db.bind._ignore_rbac = True

        # 1. Lookup deposit account
        deposit_acc = self.db.query(Account).filter(
            Account.id == uuid.UUID(source_account_id),
            Account.user_id == user.id
        ).first()
        if not deposit_acc:
            raise HTTPException(status_code=404, detail="Source deposit account not found.")

        # 2. Check sufficient funds
        if deposit_acc.cleared_balance_cents < amount_cents:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient funds in source account. Available: {deposit_acc.cleared_balance_cents} cents."
            )

        # 3. Lookup credit account
        from models.credit_card import CreditAccount, PostedTransaction
        credit_acc = self.db.query(CreditAccount).filter(
            CreditAccount.id == uuid.UUID(credit_account_id),
            CreditAccount.customer_id == user.id
        ).first()
        if not credit_acc:
            raise HTTPException(status_code=404, detail="Target credit account not found.")

        # 4. Perform atomic double-entry ledger update on checking/savings
        tx = Transaction(
            idempotency_key=f"IDEMP-PAY-{uuid.uuid4().hex}",
            user_id=user.id,
            status="COMPLETED",
            description=f"Credit Card Bill Payment to Account ending in {str(credit_acc.id)[-4:]}"
        )
        self.db.add(tx)
        self.db.flush()

        debit_split = AccountLedgerEntry(
            transaction_id=tx.id,
            account_id=deposit_acc.id,
            amount_cents=-amount_cents,
            entry_type="CREDIT"
        )
        self.db.add(debit_split)
        deposit_acc.cleared_balance_cents -= amount_cents

        # 5. Decrement debt on credit card account and restore available credit
        credit_acc.cleared_balance_cents -= amount_cents
        from services.card_network import recalculate_available_credit
        recalculate_available_credit(self.db, credit_acc)

        card_payment_tx = PostedTransaction(
            account_id=credit_acc.id,
            amount_cents=amount_cents,
            description="Bill Payment Received - Thank You"
        )
        self.db.add(card_payment_tx)

        from utils.audit import record_audit_event
        record_audit_event(
            self.db,
            "BILL_PAYMENT_EXECUTED",
            {
                "source_account_id": source_account_id,
                "credit_account_id": credit_account_id,
                "amount_cents": amount_cents
            }
        )

        self.db.commit()

        return {
            "status": "SUCCESS",
            "message": "Bill payment successfully processed.",
            "source_cleared_balance_cents": deposit_acc.cleared_balance_cents,
            "credit_cleared_balance_cents": credit_acc.cleared_balance_cents,
            "credit_available_credit_cents": credit_acc.available_credit_cents
        }

    def get_deposit_transactions(self, token: ValidatedToken, account_id: str) -> list[Dict[str, Any]]:
        # Resolve internal User entity
        user = self.db.query(User).filter(User.auth_provider_uid == token.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User profile not found.")
            
        # Ensure account belongs to user
        account = self.db.query(Account).filter(Account.id == account_id, Account.user_id == user.id).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")
            
        # Fetch ledger entries
        entries = self.db.query(AccountLedgerEntry).filter(AccountLedgerEntry.account_id == account.id).order_by(AccountLedgerEntry.posted_at.desc()).all()
        
        results = []
        running_bal = account.cleared_balance_cents
        for entry in entries:
            results.append({
                "entry_id": str(entry.entry_id),
                "transaction_id": str(entry.transaction_id),
                "amount_cents": entry.amount_cents,
                "entry_type": entry.entry_type, # 'DEBIT', 'CREDIT'
                "description": entry.transaction.description if entry.transaction else "Posted Transaction",
                "posted_at": entry.posted_at.isoformat() if entry.posted_at else "",
                "running_balance_cents": running_bal
            })
            running_bal -= entry.amount_cents # Move balance backward
            
        return results
