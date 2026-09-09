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

"""Same-currency payment initiation and authoritative simulator disposition."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi import HTTPException
from models.money import CURRENCY_EXPONENTS, MAX_MINOR, Money, from_legacy_usd


class BillPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_account_id: str
    credit_account_id: str
    money: Money | None = None
    amount_cents: int | None = Field(None, strict=True, gt=0, le=MAX_MINOR, json_schema_extra={"deprecated": True})

    @model_validator(mode="before")
    @classmethod
    def validate_currency(cls, data):
        if isinstance(data, dict) and isinstance(data.get("money"), dict):
            code = data["money"].get("currency_code")
            if not isinstance(code, str) or code not in CURRENCY_EXPONENTS:
                raise HTTPException(status_code=400, detail="Unsupported or malformed currency.")
        return data

    @model_validator(mode="after")
    def exclusive_forms(self):
        if ("money" in self.model_fields_set) == ("amount_cents" in self.model_fields_set):
            raise ValueError("Send exactly one Money value or legacy USD amount")
        if self.money is None and self.amount_cents is None:
            raise ValueError("Payment amount is required")
        if self.money is not None and self.money.amount_minor <= 0:
            raise ValueError("Payment amount must be positive")
        return self

    def payment_money(self) -> Money:
        return self.money if self.money is not None else from_legacy_usd(self.amount_cents)


class BillPaymentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["SUCCESS"] = "SUCCESS"
    disposition: Literal["POSTED"] = "POSTED"
    transaction_id: str
    money: Money
    source_cleared_balance: Money
    credit_cleared_balance: Money
    credit_available_credit: Money
    message: str = "Bill payment successfully processed."


class BillPaymentResponse(BillPaymentResult):
    """Temporary external USD projection, removed after demo qualification."""
    source_cleared_balance_cents: int | None = None
    credit_cleared_balance_cents: int | None = None
    credit_available_credit_cents: int | None = None
