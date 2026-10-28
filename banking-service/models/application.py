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

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class MortgageProductType(str, Enum):
    residential_mortgage = "RESIDENTIAL_MORTGAGE"


class ProductCategory(str, Enum):
    MORTGAGE = "MORTGAGE"
    CREDIT_CARD = "CREDIT_CARD"
    DEPOSIT = "DEPOSIT"
    LOAN = "LOAN"
    CARD = "CARD"
    GENERAL = "GENERAL"
    # Backwards compatibility aliases for lower-case attribute access if any
    mortgage = "MORTGAGE"
    credit_card = "CREDIT_CARD"
    deposit = "DEPOSIT"
    loan = "LOAN"
    card = "CARD"
    general = "GENERAL"


CARD_PRODUCT_CATEGORIES = frozenset({ProductCategory.CARD, ProductCategory.CREDIT_CARD})


class ApplicationCreateRequest(BaseModel):
    """Card applications name a catalog product code in ``product_type``.

    Shape is validated here; whether a card code is an active catalog product
    is checked by OriginationService against catalog.credit_products.
    """

    product_category: ProductCategory
    product_type: str = Field(pattern=r"^[A-Z0-9_]{1,50}$")
    requested_amount: float | None = Field(default=None, gt=0)

    @property
    def is_card_application(self) -> bool:
        return self.product_category in CARD_PRODUCT_CATEGORIES

    @model_validator(mode="after")
    def _non_card_types_are_known(self) -> "ApplicationCreateRequest":
        if self.is_card_application:
            return self
        if self.product_type not in {t.value for t in MortgageProductType}:
            raise ValueError(
                f"product_type {self.product_type!r} is not valid for category {self.product_category.value}"
            )
        return self


class ApplicationUpdateRequest(BaseModel):
    requested_amount: float | None = Field(default=None, gt=0)
    application_status: str | None = Field(default=None)


