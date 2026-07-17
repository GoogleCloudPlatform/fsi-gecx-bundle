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
import json
import hashlib
import logging
from typing import Dict, Any, List
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from models.origination import Account, Transaction
from services.financial_journal import JournalEntrySpec, post_financial_transaction
from utils.audit import record_audit_event

logger = logging.getLogger(__name__)


class LedgerService:
    def __init__(self, db: Session):
        self.db = db

    def acquire_account_locks(self, account_ids: List[str | uuid.UUID]) -> Dict[str, Account]:
        """
        Acquires pessimistic row locks on universal accounts sorted lexicographically by ID.
        Uses SELECT ... FOR UPDATE NOWAIT to prevent deadlocks and connection exhaustion.
        """
        sorted_ids_str = sorted([str(aid) for aid in set(account_ids) if aid is not None])
        sorted_uuid_objs = [uuid.UUID(s) if isinstance(s, str) else s for s in sorted_ids_str]
        
        try:
            query = self.db.query(Account).filter(
                Account.id.in_(sorted_uuid_objs)
            ).order_by(Account.id)
            
            # Use with_for_update(nowait=True) if supported by dialect
            if self.db.bind and self.db.bind.dialect.name != 'sqlite':
                query = query.with_for_update(nowait=True)
                
            accounts = query.all()
        except OperationalError as e:
            logger.warning(f"Could not acquire lock on accounts {sorted_ids_str}: {e}")
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Account concurrency lock conflict or timeout. Please retry.")

        if len(accounts) != len(sorted_ids_str):
            raise HTTPException(status_code=404, detail="One or more specified accounts were not found.")

        return {str(acc.id): acc for acc in accounts}

    def execute_transfer(
        self,
        source_account_id: str | uuid.UUID,
        dest_account_id: str | uuid.UUID,
        amount_cents: int,
        description: str,
        idempotency_key: str,
        user_id: str | uuid.UUID | None = None,
        request_payload: Dict[Any, Any] | None = None
    ) -> Dict[str, Any]:
        """
        Executes an immutable double-entry journal transfer between two universal accounts.
        Enforces idempotency, pessimistic row locking, and balance invariants.
        """
        if amount_cents <= 0:
            raise HTTPException(status_code=400, detail="Transfer amount must be positive.")

        req_hash = None
        if request_payload is not None:
            req_hash = hashlib.sha256(json.dumps(request_payload, sort_keys=True).encode("utf-8")).hexdigest()

        # 1. Idempotency check
        existing_tx = self.db.query(Transaction).filter(
            Transaction.idempotency_key == idempotency_key
        ).first()

        if existing_tx:
            if req_hash and existing_tx.request_hash and req_hash != existing_tx.request_hash:
                raise HTTPException(status_code=409, detail="Idempotency key collision with altered parameters.")
            if existing_tx.response_payload:
                return json.loads(existing_tx.response_payload)

        # 2. Acquire locks lexicographically
        locks = self.acquire_account_locks([source_account_id, dest_account_id])
        src_acc = locks[str(source_account_id)]
        dst_acc = locks[str(dest_account_id)]

        # 3. Verify balance constraints
        if src_acc.account_type in ('CHECKING', 'SAVINGS'):
            if src_acc.cleared_balance_cents < amount_cents:
                raise HTTPException(status_code=422, detail="Insufficient cash funds in checking/savings account.")
        elif src_acc.account_type == 'CREDIT_CARD':
            if src_acc.available_credit_cents < amount_cents:
                raise HTTPException(status_code=422, detail="Insufficient available credit.")

        # 4. Atomically append the balanced canonical journal and outbox event.
        posting = post_financial_transaction(
            self.db,
            idempotency_key=idempotency_key,
            user_id=user_id if user_id else src_acc.user_id,
            description=description,
            source_type="ACCOUNT_TRANSFER",
            source_references={
                "source_account_id": str(src_acc.id),
                "destination_account_id": str(dst_acc.id),
            },
            currency=src_acc.currency or "USD",
            entries=(
                JournalEntrySpec(src_acc.id, "DEBIT", amount_cents),
                JournalEntrySpec(dst_acc.id, "CREDIT", amount_cents),
            ),
        )
        tx = posting.transaction
        tx.request_hash = req_hash

        # 5. Update cached account balances
        if src_acc.account_type in ('CHECKING', 'SAVINGS'):
            src_acc.cleared_balance_cents -= amount_cents
        elif src_acc.account_type == 'CREDIT_CARD':
            src_acc.available_credit_cents -= amount_cents
            src_acc.cleared_balance_cents += amount_cents

        if dst_acc.account_type in ('CHECKING', 'SAVINGS'):
            dst_acc.cleared_balance_cents += amount_cents
        elif dst_acc.account_type == 'CREDIT_CARD':
            dst_acc.available_credit_cents += amount_cents
            dst_acc.cleared_balance_cents -= amount_cents

        result = {
            "status": "SUCCESS",
            "transaction_id": str(tx.id),
            "source_account_id": str(src_acc.id),
            "dest_account_id": str(dst_acc.id),
            "amount_cents": amount_cents,
            "idempotency_key": idempotency_key
        }

        tx.response_payload = json.dumps(result)
        tx.response_status = 200

        record_audit_event(self.db, "MONETARY_TRANSFER_EXECUTED", result)

        try:
            self.db.commit()
        except OperationalError as e:
            logger.warning(f"Commit lock conflict or timeout: {e}")
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Account concurrency lock conflict or timeout. Please retry.")
        return result
