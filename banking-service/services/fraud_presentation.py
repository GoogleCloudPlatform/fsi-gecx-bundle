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

"""Reference summary of immutable facts, not a mandatory spoken script."""
from models.money import Money
from services.money_presentation import project_money


def fraud_proposal_summary(*, card_last_four: str, facts: list[dict], issue_replacement: bool, escalate: bool) -> str:
    if not facts:
        return (f"Recognize all reviewed activity on card ending in {card_last_four}. "
                "No fraud dispute or replacement card will be opened.")
    descriptions = []
    for fact in facts:
        transaction = Money.model_validate(fact["money"])
        billing = Money.model_validate(fact["billing_money"])
        text = f"{project_money(transaction)['display_text']} at {fact['merchant_name']}"
        if transaction != billing:
            text += f"; billed to your account as {project_money(billing)['display_text']}"
        descriptions.append(text)
    summary = f"Dispute {'; '.join(descriptions)} on card ending in {card_last_four}."
    if issue_replacement:
        summary += " Block the current card and issue a replacement virtual card."
    if escalate:
        summary += " Request specialist review."
    return summary
