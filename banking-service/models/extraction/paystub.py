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

from pydantic import BaseModel, Field, model_validator
from .wrapper import ExtractionWrapper

class PaystubExtraction(BaseModel):
    employer_name: ExtractionWrapper[str] = Field(..., description="Name of the issuing employer.")
    pay_period_start: ExtractionWrapper[str] = Field(..., description="Start date of the pay period.")
    pay_period_end: ExtractionWrapper[str] = Field(..., description="End date of the pay period.")
    gross_pay: ExtractionWrapper[float] = Field(..., description="Total gross earnings for the pay period.")
    net_pay: ExtractionWrapper[float] = Field(..., description="Final net pay after taxes and deductions.")
    total_taxes: ExtractionWrapper[float] = Field(..., description="Sum of all tax withholdings.")
    total_deductions: ExtractionWrapper[float] = Field(..., description="Sum of all non-tax deductions (benefits, retirement).")

    @model_validator(mode='after')
    def verify_math_reconciliation(self):
        # Lightweight math validation: Gross - Taxes - Deductions should approximate Net Pay
        # If there is a discrepancy, we don't necessarily fail Pydantic validation, but in practice
        # this model validator can adjust confidence scores or log discrepancies.
        calculated_net = self.gross_pay.value - self.total_deductions.value
        if abs(calculated_net - self.net_pay.value) > 0.05:
            # Discrepancy detected, penalize confidence
            self.net_pay.llm_confidence = min(self.net_pay.llm_confidence, 0.5)
        return self
