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

"""Canonical integer Money with a bounded historical USD reader."""

from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

# The common range supported losslessly by PostgreSQL BIGINT and JS numbers.
MAX_MINOR = 2**53 - 1
CurrencyCode = Literal["USD", "MXN", "JPY", "BHD"]
CURRENCY_EXPONENTS = MappingProxyType({"USD": 2, "MXN": 2, "JPY": 0, "BHD": 3})
MinorAmount = Annotated[StrictInt, Field(ge=-MAX_MINOR, le=MAX_MINOR)]


class Money(BaseModel):
    """Signed value; journal entry amounts are positive with separate direction."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_schema_extra={"examples": [
            {"amount_minor": 149900, "currency_code": "USD"},
            {"amount_minor": 125, "currency_code": "JPY"},
            {"amount_minor": 1234, "currency_code": "BHD"},
        ]},
    )
    amount_minor: MinorAmount
    currency_code: CurrencyCode

    @property
    def exponent(self) -> int:
        return CURRENCY_EXPONENTS[self.currency_code]


def from_legacy_usd(amount_cents: int) -> Money:
    """Read immutable historical USD values without numeric coercion."""
    return Money(amount_minor=amount_cents, currency_code="USD")


def money_fields(name: str, money: Money) -> dict:
    """Serialize only the canonical named Money field."""
    return {name: money.model_dump(mode="json")}
