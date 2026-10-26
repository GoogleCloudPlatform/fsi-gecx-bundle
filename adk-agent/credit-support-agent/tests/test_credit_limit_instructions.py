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

from agent.instructions import compose_session_instruction


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
