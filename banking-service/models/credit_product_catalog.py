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

"""Credit product catalog contract: seed validation and public read DTOs.

Rates are fractions (``0.2249`` == 22.49%). Money amounts are integer minor
units of the product's ``currency_code``. A ``None`` intro or penalty APR
means the product has none; clients must not substitute a default.
"""
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from models.money import CurrencyCode, MAX_MINOR, Money

ProductCode = Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,50}$")]
Rate = Annotated[Decimal, Field(ge=0, le=1, max_digits=5, decimal_places=4)]
MinorAmount = Annotated[StrictInt, Field(ge=0, le=MAX_MINOR)]
FeatureText = Annotated[str, Field(min_length=1, max_length=200)]


class CreditProductSeed(BaseModel):
    """One row of resources/data/credit_products.json; field names match the table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    product_code: ProductCode
    product_name: str = Field(min_length=1, max_length=100)
    display_order: StrictInt = Field(ge=0)
    tagline: str = Field(min_length=1, max_length=160)
    best_for: str = Field(min_length=1, max_length=200)
    currency_code: CurrencyCode
    min_credit_limit_cents: MinorAmount = Field(gt=0)
    max_credit_limit_cents: MinorAmount
    purchase_apr: Rate
    intro_purchase_apr: Rate | None
    intro_purchase_apr_months: StrictInt | None = Field(gt=0)
    intro_balance_transfer_apr: Rate | None
    intro_balance_transfer_apr_months: StrictInt | None = Field(gt=0)
    balance_transfer_fee_rate: Rate
    balance_transfer_fee_minimum_minor: MinorAmount
    cash_advance_apr: Rate
    cash_advance_fee_rate: Rate
    cash_advance_fee_minimum_minor: MinorAmount
    foreign_transaction_fee_rate: Rate
    late_fee_maximum_minor: MinorAmount
    returned_payment_fee_maximum_minor: MinorAmount
    penalty_apr: Rate | None
    annual_fee_cents: MinorAmount
    cashback_rate: Rate
    travel_multiplier: StrictInt = Field(ge=1)
    dining_multiplier: StrictInt = Field(ge=1)
    is_secured: bool
    features: list[FeatureText] = Field(min_length=1)
    is_active: bool

    @model_validator(mode="after")
    def _coherent_terms(self) -> "CreditProductSeed":
        if self.min_credit_limit_cents > self.max_credit_limit_cents:
            raise ValueError(f"{self.product_code}: minimum limit exceeds maximum limit")
        for offer in ("intro_purchase_apr", "intro_balance_transfer_apr"):
            if (getattr(self, offer) is None) != (getattr(self, f"{offer}_months") is None):
                raise ValueError(f"{self.product_code}: {offer} and its months must be set together")
        earns_points = self.travel_multiplier > 1 or self.dining_multiplier > 1
        if earns_points and self.cashback_rate > 0:
            raise ValueError(f"{self.product_code}: a product earns either cash back or points, not both")
        return self


class MoneyPresentation(BaseModel):
    """Same shape as services.money_presentation.project_money."""

    money: Money
    locale: str
    display_text: str


class RatePresentation(BaseModel):
    rate: str = Field(description="Fraction with four decimal places, e.g. '0.2249'.")
    display_text: str = Field(description="Percentage, e.g. '22.49%'.")


class IntroAprPresentation(BaseModel):
    apr: RatePresentation
    months: int
    display_text: str


class RewardsPresentation(BaseModel):
    type: Literal["CASHBACK", "POINTS", "NONE"]
    cashback_rate: RatePresentation
    travel_multiplier: int
    dining_multiplier: int
    display_text: str


class CreditProductResponse(BaseModel):
    product_code: str
    product_name: str
    display_order: int
    tagline: str
    best_for: str
    is_secured: bool
    currency_code: CurrencyCode
    features: list[str]
    min_credit_limit: MoneyPresentation
    max_credit_limit: MoneyPresentation
    annual_fee: MoneyPresentation
    purchase_apr: RatePresentation
    intro_purchase_apr: IntroAprPresentation | None
    intro_balance_transfer_apr: IntroAprPresentation | None
    penalty_apr: RatePresentation | None
    balance_transfer_fee_rate: RatePresentation
    balance_transfer_fee_minimum: MoneyPresentation
    cash_advance_apr: RatePresentation
    cash_advance_fee_rate: RatePresentation
    cash_advance_fee_minimum: MoneyPresentation
    foreign_transaction_fee_rate: RatePresentation
    late_fee_maximum: MoneyPresentation
    returned_payment_fee_maximum: MoneyPresentation
    rewards: RewardsPresentation


class CreditProductListResponse(BaseModel):
    """Active products only, ordered by ``display_order`` then ``product_code``."""

    products: list[CreditProductResponse]
