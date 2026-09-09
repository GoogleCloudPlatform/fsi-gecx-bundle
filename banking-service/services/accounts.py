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

import hashlib
import json
import uuid
import random
import datetime
import logging
from typing import Dict, Any
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError
from models.payment import BillPaymentResult

from models.identity import User
from models.origination import Account, AccountLedgerEntry, Application, DepositApplication, Transaction
from models.authentication import ValidatedToken
from repositories.accounts import AccountsRepository
from services.profile import ProfileService
from utils.database import enable_session_rbac_override
from utils.internal_execution import InternalServiceContext, apply_internal_db_access
from models.money import Money, money_fields
from services.financial_journal import (
    JournalEntrySpec,
    ensure_credit_journal_account,
    ensure_system_journal_account,
    post_financial_transaction,
)

logger = logging.getLogger(__name__)


class DepositAccountCreateRequest(BaseModel):
    account_type: str = Field(..., description="CHECKING or SAVINGS")
    product_name: str = Field(..., description="Name of the banking product")
    member_type: str = Field("current", description="current or new")
    initial_deposit_cents: int = Field(0, ge=0, description="Initial funding deposit in cents")


class AccountsService:
    def __init__(self, db: Session):
        self.db = db
        self.accounts_repo = AccountsRepository(db)

    def execute_bill_payment_for_user(
        self,
        user: User,
        source_account_id: str,
        credit_account_id: str,
        money: Money,
        idempotency_key: str,
        internal_context: InternalServiceContext | None = None,
    ) -> Dict[str, Any]:
        if not isinstance(money, Money) or money.amount_minor <= 0:
            raise HTTPException(status_code=400, detail="Payment requires positive Money.")
        if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 128:
            raise HTTPException(status_code=400, detail="A non-empty Idempotency-Key (max 128 characters) is required.")
        try:
            source_account_id = str(uuid.UUID(source_account_id))
            credit_account_id = str(uuid.UUID(credit_account_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Account identifiers must be UUIDs.") from exc
        user_id = user.id
        durable_key = "bill-payment:" + hashlib.sha256(f"{user_id}:{idempotency_key}".encode()).hexdigest()
        request_hash = hashlib.sha256(json.dumps({
            "source_account_id": source_account_id, "credit_account_id": credit_account_id,
            "money": money.model_dump(),
        }, sort_keys=True).encode()).hexdigest()

        def replay():
            existing = self.db.query(Transaction).filter(Transaction.idempotency_key == durable_key).one_or_none()
            if existing is None:
                return None
            if existing.request_hash != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency key reused with different account, amount, or currency.")
            if not existing.response_payload:
                raise HTTPException(status_code=409, detail="Payment is in progress. Retry with the same key.")
            return BillPaymentResult.model_validate_json(existing.response_payload).model_dump(mode="json")

        try:
            if internal_context is not None:
                apply_internal_db_access(self.db, internal_context, "simulation:autopaydown")
            previous = replay()
            if previous is not None:
                return previous
            deposit_acc = self.accounts_repo.get_deposit_account_for_user(user_id, source_account_id, lock=True)
            if deposit_acc is None or deposit_acc.account_type not in ("CHECKING", "SAVINGS"):
                raise HTTPException(status_code=404, detail="Source deposit account not found.")
            credit_acc = self.accounts_repo.get_credit_account_for_user(user_id, credit_account_id, lock=True)
            if credit_acc is None:
                raise HTTPException(status_code=404, detail="Target credit account not found.")
            previous = replay()
            if previous is not None:
                return previous
            if deposit_acc.currency != money.currency_code or credit_acc.currency != money.currency_code:
                raise HTTPException(status_code=422, detail="Payment and both account currencies must match.")
            amount = money.amount_minor
            if deposit_acc.cleared_balance_cents < amount:
                raise HTTPException(status_code=422, detail="Insufficient funds in source account.")
            if credit_acc.cleared_balance_cents < amount:
                raise HTTPException(status_code=422, detail="Payment exceeds outstanding card balance.")
            # Lock the existing mirror before its cached fields can be synchronized.
            mirror = self.db.query(Account).filter(Account.credit_account_id == credit_acc.id).populate_existing().with_for_update(nowait=True).one_or_none()
            if mirror is not None and mirror.currency != money.currency_code:
                raise HTTPException(status_code=422, detail="Card journal denomination mismatch.")
            credit_journal_acc = ensure_credit_journal_account(self.db, credit_acc)
            posting = post_financial_transaction(
                self.db, idempotency_key=durable_key, user_id=user_id,
                description=f"Credit Card Bill Payment to Account ending in {str(credit_acc.id)[-4:]}",
                source_type="CREDIT_CARD_BILL_PAYMENT", currency=money.currency_code,
                source_references={"source_account_id": source_account_id, "credit_account_id": credit_account_id},
                entries=(JournalEntrySpec(deposit_acc.id, "DEBIT", money),
                         JournalEntrySpec(credit_journal_acc.id, "CREDIT", money)),
            )
            deposit_acc.cleared_balance_cents -= amount
            credit_acc.cleared_balance_cents -= amount
            from services.card_network import recalculate_available_credit
            recalculate_available_credit(self.db, credit_acc)
            credit_journal_acc.cleared_balance_cents = credit_acc.cleared_balance_cents
            credit_journal_acc.available_credit_cents = credit_acc.available_credit_cents
            from models.credit_card import PostedTransaction
            statement = self.accounts_repo.add_posted_transaction(PostedTransaction(
                account_id=credit_acc.id, journal_transaction_id=posting.transaction.id,
                amount_cents=amount, description="Bill Payment Received - Thank You",
            ))
            result = BillPaymentResult(
                transaction_id=str(posting.transaction.id), money=money,
                source_cleared_balance=Money(amount_minor=deposit_acc.cleared_balance_cents, currency_code=money.currency_code),
                credit_cleared_balance=Money(amount_minor=credit_acc.cleared_balance_cents, currency_code=money.currency_code),
                credit_available_credit=Money(amount_minor=credit_acc.available_credit_cents, currency_code=money.currency_code),
            )
            posting.transaction.request_hash = request_hash
            posting.transaction.response_payload = result.model_dump_json()
            posting.transaction.response_status = 200
            from utils.audit import record_audit_event
            record_audit_event(self.db, "BILL_PAYMENT_EXECUTED", {
                "source_account_id": source_account_id, "credit_account_id": credit_account_id,
                "money": money.model_dump(), "transaction_id": str(posting.transaction.id),
                "statement_transaction_id": str(statement.id),
            })
            self.db.commit()
            return result.model_dump(mode="json")
        except OperationalError as exc:
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Account lock conflict. Retry with the same Idempotency-Key.") from exc
        except IntegrityError as exc:
            self.db.rollback()
            previous = replay()
            if previous is not None:
                return previous
            raise HTTPException(status_code=409, detail="Concurrent payment conflict. Retry with the same Idempotency-Key.") from exc
        except Exception:
            self.db.rollback()
            raise

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

        # If initial funding is provided, credit the deposit liability and debit
        # the external-funding clearing account in the canonical journal.
        if request.initial_deposit_cents > 0:
            sys_acc = ensure_system_journal_account(
                self.db,
                "SYSTEM_EXTERNAL_FUNDING",
                "External funding clearing counterparty",
                currency=new_acc.currency,
            )
            post_financial_transaction(
                self.db,
                idempotency_key=idempotency_key or f"IDEMP-DEP-{uuid.uuid4().hex}",
                user_id=user.id,
                description=f"Initial deposit funding for {request.product_name}",
                source_type="INITIAL_DEPOSIT_FUNDING",
                source_references={"account_id": str(new_acc.id), "application_id": str(app.id)},
                currency=new_acc.currency or "USD",
                entries=(
                    JournalEntrySpec(sys_acc.id, "DEBIT", Money(amount_minor=request.initial_deposit_cents, currency_code=new_acc.currency)),
                    JournalEntrySpec(new_acc.id, "CREDIT", Money(amount_minor=request.initial_deposit_cents, currency_code=new_acc.currency)),
                ),
            )
            sys_acc.cleared_balance_cents += request.initial_deposit_cents

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

        enable_session_rbac_override(self.db)

        # Fetch checking/savings accounts
        deposit_accounts = self.db.query(Account).filter(
            Account.user_id == user.id,
            Account.status == "ACTIVE",
            Account.account_type.in_(["CHECKING", "SAVINGS"]),
        ).all()

        # Fetch credit accounts
        from models.credit_card import CreditAccount
        credit_accounts = self.db.query(CreditAccount).filter(
            CreditAccount.customer_id == user.id,
            CreditAccount.status == "ACTIVE",
        ).all()

        # Closed suites are intentionally retained for ledger/audit history. Their
        # presence must suppress the local-development convenience auto-provisioner
        # so a presenter can demonstrate the explicit one-click provisioning state.
        has_archived_or_active_suite = bool(
            self.db.query(Account).filter(Account.user_id == user.id).first()
            or self.db.query(CreditAccount).filter(
                CreditAccount.customer_id == user.id
            ).first()
        )

        # Auto-provision sandbox for mock user when running locally to speed up local dev onboarding!
        from utils.env import is_running_locally
        if (
            is_running_locally()
            and not deposit_accounts
            and not credit_accounts
            and not has_archived_or_active_suite
        ):
            user_email = user.email
            user_uid = user.auth_provider_uid
            user_id = user.id
            logger.info(f"Auto-provisioning local sandbox for user: {user_email}")
            from services.seeding_service import provision_user_suite
            try:
                provision_user_suite(self.db, user_email, user_uid)
                self.db.commit()
                # Fetch accounts again
                deposit_accounts = self.db.query(Account).filter(
                    Account.user_id == user_id,
                    Account.status == "ACTIVE",
                ).all()
                credit_accounts = self.db.query(CreditAccount).filter(
                    CreditAccount.customer_id == user_id,
                    CreditAccount.status == "ACTIVE",
                ).all()
            except Exception as e:
                logger.error(f"Failed to auto-provision local sandbox for user: {user_email}. Error: {e}")
                self.db.rollback()

        from repositories.credit_card import CreditCardRepository
        from services.credit_card import get_wallet_status_by_card_token

        credit_repo = CreditCardRepository(self.db)
        for cred_acc in credit_accounts:
            credit_repo.recalculate_available_credit(cred_acc)

        wallet_status_by_account = {
            str(cred_acc.id): get_wallet_status_by_card_token(self.db, str(cred_acc.id))
            for cred_acc in credit_accounts
        }
        now = datetime.datetime.now(datetime.timezone.utc)

        return {
            "deposit_accounts": [
                {
                    "account_id": str(acc.id),
                    "account_number": acc.account_number,
                    "account_type": acc.account_type,
                    "product_name": acc.product_name,
                    "product_code": acc.product_code,
                    "currency_code": acc.currency,
                    **money_fields("cleared_balance", Money(amount_minor=acc.cleared_balance_cents, currency_code=acc.currency)),
                    "routing_number": acc.routing_number,
                    "status": acc.status
                } for acc in deposit_accounts
            ],
            "credit_accounts": [
                {
                    "account_id": str(cred_acc.id),
                    "product_code": cred_acc.product_code,
                    "currency_code": cred_acc.currency,
                    "status": cred_acc.status,
                    **money_fields("credit_limit", Money(amount_minor=cred_acc.credit_limit_cents, currency_code=cred_acc.currency)),
                    **money_fields("cleared_balance", Money(amount_minor=cred_acc.cleared_balance_cents, currency_code=cred_acc.currency)),
                    **money_fields("statement_balance", Money(amount_minor=max(0, cred_acc.cleared_balance_cents), currency_code=cred_acc.currency)),
                    **money_fields("minimum_due", Money(amount_minor=min(3500, max(0, cred_acc.cleared_balance_cents)), currency_code=cred_acc.currency)),
                    **money_fields("available_credit", Money(amount_minor=cred_acc.available_credit_cents, currency_code=cred_acc.currency)),
                    "payment_due_date": (cred_acc.payment_due_date or (now + datetime.timedelta(days=15))).isoformat(),
                    "statement_close_date": (cred_acc.statement_close_date or (now - datetime.timedelta(days=15))).isoformat(),
                    "cards": [
                        {
                            "card_id": str(card.id),
                            "cardholder_name": card.cardholder_name,
                            "last_four": card.last_four,
                            "card_token": card.card_token,
                            "status": card.status,
                            "is_active": card.is_active,
                            "is_virtual": card.is_virtual,
                            "exp_month": card.exp_month,
                            "exp_year": card.exp_year,
                            **wallet_status_by_account.get(str(cred_acc.id), {}).get(card.card_token, {}),
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
        money: Money,
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """
        Executes a credit card bill payment from a checking or savings deposit account.
        Subtracts from deposit balance, reduces credit account cleared debt balance, and restores available credit.
        """
        # Resolve internal User entity
        user = self.accounts_repo.get_user_by_auth_provider_uid(token.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User profile not resolved.")

        try:
            return self.execute_bill_payment_for_user(user, source_account_id, credit_account_id, money, idempotency_key)
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error during bill payment transaction: {e}")
            raise e

    def get_deposit_transactions(self, token: ValidatedToken, account_id: str) -> list[Dict[str, Any]]:
        # Resolve internal User entity
        user = self.db.query(User).filter(User.auth_provider_uid == token.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User profile not found.")
            
        # Ensure account belongs to user
        account = self.db.query(Account).filter(
            Account.id == account_id,
            Account.user_id == user.id,
            Account.status == "ACTIVE",
        ).first()
        if not account:
            raise HTTPException(status_code=404, detail="Account not found.")
            
        # Fetch ledger entries
        entries = self.db.query(AccountLedgerEntry).filter(AccountLedgerEntry.account_id == account.id).order_by(AccountLedgerEntry.posted_at.desc()).all()
        
        results = []
        running_bal = account.cleared_balance_cents
        for entry in entries:
            is_pending = entry.transaction.status == "PENDING" if entry.transaction else False
            results.append({
                "entry_id": str(entry.entry_id),
                "transaction_id": str(entry.transaction_id),
                "money": Money(amount_minor=entry.amount_minor, currency_code=account.currency).model_dump(),
                "entry_type": entry.entry_type, # 'DEBIT', 'CREDIT'
                "description": entry.transaction.description if entry.transaction else "Posted Transaction",
                "posted_at": entry.posted_at.isoformat() if entry.posted_at else "",
                "running_balance": Money(amount_minor=running_bal, currency_code=account.currency).model_dump(),
                "pending": is_pending
            })
            if not is_pending:
                signed_minor = entry.amount_minor if entry.entry_type == "CREDIT" else -entry.amount_minor
                running_bal -= signed_minor  # Undo this posting to recover the prior balance.
            
        return results
