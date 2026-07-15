from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from models.credit_card import CreditAccount, PostedTransaction
from models.identity import User
from models.origination import Account, AccountLedgerEntry, Transaction


class AccountsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_auth_provider_uid(self, auth_provider_uid: str) -> User | None:
        return self.db.query(User).filter(User.auth_provider_uid == auth_provider_uid).first()

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def get_user_by_id(self, user_id: str | uuid.UUID) -> User | None:
        user_uuid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        return self.db.query(User).filter(User.id == user_uuid).first()

    def get_deposit_account_for_user(self, user_id: str | uuid.UUID, account_id: str | uuid.UUID) -> Account | None:
        user_uuid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        account_uuid = uuid.UUID(str(account_id)) if not isinstance(account_id, uuid.UUID) else account_id
        return self.db.query(Account).filter(
            Account.id == account_uuid,
            Account.user_id == user_uuid,
            Account.status == "ACTIVE",
        ).first()

    def list_funding_accounts_for_user(self, user_id: str | uuid.UUID) -> list[Account]:
        user_uuid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        return (
            self.db.query(Account)
            .filter(
                Account.user_id == user_uuid,
                Account.status == "ACTIVE",
                Account.account_type.in_(["CHECKING", "SAVINGS"]),
            )
            .all()
        )

    def get_credit_account_for_user(
        self,
        user_id: str | uuid.UUID,
        credit_account_id: str | uuid.UUID,
    ) -> CreditAccount | None:
        user_uuid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        account_uuid = uuid.UUID(str(credit_account_id)) if not isinstance(credit_account_id, uuid.UUID) else credit_account_id
        return self.db.query(CreditAccount).filter(
            CreditAccount.id == account_uuid,
            CreditAccount.customer_id == user_uuid,
            CreditAccount.status == "ACTIVE",
        ).first()

    def add_transaction(self, transaction: Transaction) -> Transaction:
        self.db.add(transaction)
        self.db.flush()
        return transaction

    def add_account_ledger_entry(self, entry: AccountLedgerEntry) -> AccountLedgerEntry:
        self.db.add(entry)
        self.db.flush()
        return entry

    def add_posted_transaction(self, posted_transaction: PostedTransaction) -> PostedTransaction:
        self.db.add(posted_transaction)
        self.db.flush()
        return posted_transaction
