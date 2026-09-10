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

"""Exact decimal presentation facts; agents own spoken language."""
from models.money import Money
from utils.support_locale import SUPPORTED_SUPPORT_LOCALES

SUPPORTED_VOICE_LOCALES = SUPPORTED_SUPPORT_LOCALES


def project_money(money: Money, locale: str = "en-US") -> dict:
    if not isinstance(money, Money):
        raise TypeError("A validated Money value is required")
    if locale not in SUPPORTED_VOICE_LOCALES:
        raise ValueError("Unsupported voice presentation locale")
    whole, fraction = divmod(abs(money.amount_minor), 10 ** money.exponent)
    digits = f"{whole:,}"
    if money.exponent:
        digits += f".{fraction:0{money.exponent}d}"
    if money.amount_minor < 0:
        digits = "-" + digits
    return {"money": money.model_dump(), "locale": locale,
            "display_text": f"{money.currency_code} {digits}"}


def project_transaction_money(transaction: Money, billing: Money) -> dict:
    """No FX: original purchase and authorized billing remain independent facts."""
    return {
        "money": transaction.model_dump(), "billing_money": billing.model_dump(),
        "presentations": {
            locale: {"transaction": project_money(transaction, locale),
                     "billing": project_money(billing, locale)}
            for locale in SUPPORTED_VOICE_LOCALES
        },
    }
