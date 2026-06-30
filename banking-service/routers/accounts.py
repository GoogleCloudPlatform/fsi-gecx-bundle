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

import logging
from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session

from utils.database import get_db
from utils.auth import get_current_user
from models.authentication import ValidatedToken
from services.accounts import AccountsService, DepositAccountCreateRequest
from utils.idempotency import check_idempotency_header

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/accounts", tags=["Deposit Accounts"], dependencies=[Depends(get_current_user)])
v1_router = APIRouter(prefix="/v1/accounts", tags=["Deposit Accounts"], dependencies=[Depends(get_current_user)])
alias_router = APIRouter(prefix="/accounts", tags=["Deposit Accounts"], dependencies=[Depends(get_current_user)])


def get_accounts_service(db: Session = Depends(get_db)) -> AccountsService:
    return AccountsService(db)


@router.post("/deposit", status_code=status.HTTP_201_CREATED)
@v1_router.post("/deposit", status_code=status.HTTP_201_CREATED)
@alias_router.post("/deposit", status_code=status.HTTP_201_CREATED)
async def create_deposit_account(
    request: DepositAccountCreateRequest,
    response: Response,
    service: AccountsService = Depends(get_accounts_service),
    token: ValidatedToken = Depends(get_current_user),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    cached_payload: dict | None = Depends(check_idempotency_header)
):
    if cached_payload:
        response.status_code = status.HTTP_200_OK
        return cached_payload

    return service.create_deposit_account(request, token, idempotency_key=x_idempotency_key)


@router.get("/summary", status_code=status.HTTP_200_OK)
@v1_router.get("/summary", status_code=status.HTTP_200_OK)
@alias_router.get("/summary", status_code=status.HTTP_200_OK)
async def get_accounts_summary(
    service: AccountsService = Depends(get_accounts_service),
    token: ValidatedToken = Depends(get_current_user)
):
    """
    Retrieves all checking, savings, and credit accounts summary for the authenticated user context.
    """
    return service.get_user_accounts_summary(token)

