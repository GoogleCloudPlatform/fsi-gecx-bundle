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

"""Credit-limit guidance carried by the rendered voice-agent instruction."""

import pytest

from agent.instructions import (
    compose_session_instruction,
    format_credit_account_context,
)


@pytest.fixture(scope="module")
def instruction() -> str:
    return compose_session_instruction(avatar_name="Nova")


@pytest.mark.parametrize(
    "fact",
    [
        "refusal_facts",
        "product_name",
        "current_limit",
        "product_maximum",
        "max_instantly_approvable",
        "soft_tier_cap",
        "retry_after",
        "next_steps",
    ],
)
def test_refusals_are_explained_from_bank_facts(instruction, fact) -> None:
    assert fact in instruction
    assert 'Never give a generic "not eligible under current policy" answer' in instruction


@pytest.mark.parametrize(
    "reason",
    [
        "PRODUCT_LIMIT_OUT_OF_BOUNDS",
        "ABOVE_PRODUCT_MAXIMUM",
        "COOLING_OFF_ACTIVE",
        "INCOME_CONFIRMATION_REQUIRED",
    ],
)
def test_each_refusal_reason_has_guidance(instruction, reason) -> None:
    assert reason in instruction


def test_soft_and_hard_inquiry_disclosures_require_consent(instruction) -> None:
    assert "SOFT_INQUIRY_CONSENT_ON_CONFIRMATION" in instruction
    assert "HARD_INQUIRY_CONSENT_ON_CONFIRMATION" in instruction
    assert "soft credit check is required and that it will not affect their credit score" in instruction
    assert "hard credit inquiry is required and that it may affect their credit score" in instruction
    assert "Confirming that proposal is the customer's consent to the credit check" in instruction
    assert "Never assume or infer consent" in instruction
    assert "pre-approved headroom (inquiry type NONE) needs no credit bureau check" in instruction


def test_counteroffers_need_explicit_confirmation_of_the_new_amount(instruction) -> None:
    assert (
        "state the exact bank-returned amount and get the customer's explicit "
        "confirmation of that new amount"
    ) in instruction


def test_non_retryable_refusal_is_never_blindly_retried(instruction) -> None:
    assert (
        "if preparation returns success false with retryable false, do not call "
        "prepare_action_proposal again with the same amount or a guessed amount"
    ) in instruction


def test_whole_dollar_speech_and_natural_offer_guidance(instruction) -> None:
    assert 'Speak whole-dollar amounts naturally without pronouncing ".00"' in instruction
    assert 'Never say "I have prepared a proposal"' in instruction
    assert 'without using internal protocol words like "proposal"' in instruction
    assert "Card product and limit inquiries:" in instruction
    assert (
        "do not claim you lack access or offer a human transfer just to look up the card product's maximum limit"
        in instruction
    )


def test_format_credit_account_context_includes_product_and_maximum_limit() -> None:
    rendered = format_credit_account_context(
        {
            "product_code": "CASH_REWARDS_VISA",
            "product_name": "Nova Horizon Cash Rewards Visa",
            "credit_limit": {
                "money": {"amount_minor": 1000000, "currency_code": "USD", "exponent": 2},
                "locale": "en-US",
                "display_text": "USD 10,000.00",
            },
            "available_credit": {
                "money": {"amount_minor": 924000, "currency_code": "USD", "exponent": 2},
                "locale": "en-US",
                "display_text": "USD 9,240.00",
            },
            "product_maximum_limit": {
                "money": {"amount_minor": 1500000, "currency_code": "USD", "exponent": 2},
                "locale": "en-US",
                "display_text": "USD 15,000.00",
            },
        }
    )
    assert rendered is not None
    assert "Card product: Nova Horizon Cash Rewards Visa (CASH_REWARDS_VISA)." in rendered
    assert "Starting credit limit: USD 10,000.00 (available credit: USD 9,240.00)." in rendered
    assert "Card product maximum credit limit: USD 15,000.00." in rendered
    assert format_credit_account_context(None) is None
    assert format_credit_account_context({}) is None
