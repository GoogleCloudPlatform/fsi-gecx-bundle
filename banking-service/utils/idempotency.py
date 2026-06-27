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

import json
import hashlib
from typing import Optional, Any, Dict
from fastapi import Header, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from utils.database import get_db
from models.origination import Transaction


async def check_idempotency_header(
    request: Request,
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    db: Session = Depends(get_db)
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency enforcing X-Idempotency-Key validation against ledger.transactions.
    If the transaction already succeeded, returns the cached payload dict or raises HTTP 409 on collision.
    If the key is new or not provided, returns None.
    """
    if not x_idempotency_key:
        return None

    existing_tx = db.query(Transaction).filter(
        Transaction.idempotency_key == x_idempotency_key
    ).first()

    if not existing_tx:
        return None

    # Try to compute payload hash from request body if available
    req_hash = None
    try:
        body_bytes = await request.body()
        if body_bytes:
            payload_json = json.loads(body_bytes.decode("utf-8"))
            req_hash = hashlib.sha256(json.dumps(payload_json, sort_keys=True).encode("utf-8")).hexdigest()
    except Exception:
        pass

    if req_hash and existing_tx.request_hash and req_hash != existing_tx.request_hash:
        raise HTTPException(status_code=409, detail="Idempotency key collision with altered parameters.")

    if existing_tx.response_payload:
        return json.loads(existing_tx.response_payload)

    return None
