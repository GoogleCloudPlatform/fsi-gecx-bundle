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
