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

from pydantic import BaseModel, Field


class ProductType(str, Enum):
    residential_mortgage = "RESIDENTIAL_MORTGAGE"
    aura_elite_reserve = "AURA_ELITE_RESERVE"
    velocity_cash_preferred = "VELOCITY_CASH_PREFERRED"
    equinox_horizon = "EQUINOX_HORIZON"
    vanguard_builder = "VANGUARD_BUILDER"


class ProductCategory(str, Enum):
    loan = "LOAN"
    card = "CARD"


class ApplicationCreateRequest(BaseModel):
    product_category: ProductCategory
    product_type: ProductType
    requested_amount: float | None = Field(default=None, gt=0)


class ApplicationUpdateRequest(BaseModel):
    requested_amount: float | None = Field(default=None, gt=0)
    application_status: str | None = Field(default=None)


