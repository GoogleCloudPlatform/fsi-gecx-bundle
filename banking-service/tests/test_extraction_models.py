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

import pytest
from pydantic import ValidationError
from models.extraction import W2Extraction, PaystubExtraction, ExtractionWrapper

def test_w2_extraction_valid_instantiation():
    data = {
        "employer_name": {"value": "Acme Corp", "source_snippet": "Acme Corp", "llm_confidence": 0.95},
        "employee_social_security_number": {"value": "000-00-0000", "source_snippet": "000-00-0000", "llm_confidence": 0.99},
        "wages_tips_other_comp": {"value": 75000.0, "source_snippet": "75000", "llm_confidence": 0.98},
        "social_security_wages": {"value": 75000.0, "source_snippet": "75000", "llm_confidence": 0.98},
        "medicare_wages_and_tips": {"value": 75000.0, "source_snippet": "75000", "llm_confidence": 0.98}
    }
    model = W2Extraction(**data)
    assert model.employer_name.value == "Acme Corp"
    assert model.wages_tips_other_comp.llm_confidence == 0.98

def test_invalid_llm_confidence_raises():
    with pytest.raises(ValidationError):
        ExtractionWrapper[str](value="Test", source_snippet="Test", llm_confidence=1.5)

def test_negative_llm_confidence_raises():
    with pytest.raises(ValidationError):
        ExtractionWrapper[str](value="Test", source_snippet="Test", llm_confidence=-0.05)

def test_paystub_math_reconciliation_success():
    data = {
        "employer_name": {"value": "Acme Corp", "source_snippet": "Acme Corp", "llm_confidence": 0.95},
        "pay_period_start": {"value": "2026-01-01", "source_snippet": "2026-01-01", "llm_confidence": 0.99},
        "pay_period_end": {"value": "2026-01-15", "source_snippet": "2026-01-15", "llm_confidence": 0.99},
        "gross_pay": {"value": 5000.0, "source_snippet": "5000", "llm_confidence": 0.99},
        "net_pay": {"value": 4000.0, "source_snippet": "4000", "llm_confidence": 0.99},
        "total_taxes": {"value": 800.0, "source_snippet": "800", "llm_confidence": 0.99},
        "total_deductions": {"value": 1000.0, "source_snippet": "1000", "llm_confidence": 0.99}
    }
    model = PaystubExtraction(**data)
    assert model.net_pay.llm_confidence == 0.99

def test_paystub_math_reconciliation_penalty():
    data = {
        "employer_name": {"value": "Acme Corp", "source_snippet": "Acme Corp", "llm_confidence": 0.95},
        "pay_period_start": {"value": "2026-01-01", "source_snippet": "2026-01-01", "llm_confidence": 0.99},
        "pay_period_end": {"value": "2026-01-15", "source_snippet": "2026-01-15", "llm_confidence": 0.99},
        "gross_pay": {"value": 5000.0, "source_snippet": "5000", "llm_confidence": 0.99},
        "net_pay": {"value": 3000.0, "source_snippet": "3000", "llm_confidence": 0.99},
        "total_taxes": {"value": 800.0, "source_snippet": "800", "llm_confidence": 0.99},
        "total_deductions": {"value": 1000.0, "source_snippet": "1000", "llm_confidence": 0.99}
    }
    model = PaystubExtraction(**data)
    assert model.net_pay.llm_confidence == 0.5
