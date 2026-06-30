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

from typing import List, Optional
from pydantic import BaseModel, Field


class PersonalFinanceCategory(BaseModel):
    primary: str
    detailed: str
    confidence_level: str = "VERY_HIGH"


class PaymentMeta(BaseModel):
    reference_number: Optional[str] = None
    auth_code: Optional[str] = None
    payment_method: Optional[str] = None


class FDXTransaction(BaseModel):
    account_id: str
    transaction_id: str
    pending_transaction_id: Optional[str] = None
    pending: bool
    amount: float = Field(..., description="Transaction amount in decimal currency format.")
    iso_currency_code: str = "USD"
    description: str
    transaction_type: str = Field(..., description="Clearing rail typology e.g. DEBITCARD, CREDITCARD, DIRECTDEPOSIT, ADJUSTMENT")
    posted_timestamp: Optional[str] = None
    transaction_timestamp: str
    personal_finance_category: Optional[PersonalFinanceCategory] = None
    payment_meta: Optional[PaymentMeta] = None


class PaginatedTransactionsResult(BaseModel):
    transactions: List[FDXTransaction]
    total: int


class PaymentNetwork(BaseModel):
    bank_id: str
    identifier: str
    type: str = "US_ACH"
    transfer_in: bool = True
    transfer_out: bool = True


class PaginatedPaymentNetworksResult(BaseModel):
    payment_networks: List[PaymentNetwork]
    total: int


class RealTimeBalanceResponse(BaseModel):
    account_id: str
    credit_limit: float
    cleared_balance: float
    pending_authorizations_amount: float
    realtime_available_credit: float
    iso_currency_code: str = "USD"


class FDXAccount(BaseModel):
    account_id: str
    account_number_display: str = Field(..., description="Masked account number e.g. '3333'")
    product_name: str
    status: str
    account_type: str = "CREDIT_CARD"
    current_balance: float
    available_credit: float
    credit_line: float
    iso_currency_code: str = "USD"


class FDXErrorResponse(BaseModel):
    code: int
    message: str
