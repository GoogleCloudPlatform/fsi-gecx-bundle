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

"""Banking-owned consequential text built from immutable proposal facts."""

import json
from pathlib import Path

from models.money import Money
from services.money_presentation import project_money, SUPPORTED_VOICE_LOCALES

CONTENT = json.loads((Path(__file__).resolve().parents[1] / "resources/data/money_fraud_voice_content.json").read_text())


def fraud_proposal_presentations(*, card_last_four: str, facts: list[dict], issue_replacement: bool, escalate: bool) -> dict:
    result = {}
    for locale in SUPPORTED_VOICE_LOCALES:
        copy = CONTENT[locale]
        projections = {}
        for kind in ("display_text", "speech_text"):
            if not facts:
                text = copy["recognized_proposal"].format(card_last_four=card_last_four)
            else:
                descriptions = []
                for fact in facts:
                    transaction = Money.model_validate(fact["money"])
                    billing = Money.model_validate(fact["billing_money"])
                    template = copy["same_currency_fact"] if transaction == billing else copy["billing_fact"]
                    descriptions.append(template.format(
                        transaction=project_money(transaction, locale)[kind],
                        billing=project_money(billing, locale)[kind],
                        merchant=fact["merchant_name"]))
                text = copy["dispute_proposal"].format(selection="; ".join(descriptions).rstrip("."), card_last_four=card_last_four)
                if issue_replacement:
                    text += " " + copy["replacement_consequence"]
                if escalate:
                    text += " " + copy["escalation_consequence"]
            projections[kind] = text
        result[locale] = {"locale": locale, "content_version": CONTENT["version"], **projections}
    return result
