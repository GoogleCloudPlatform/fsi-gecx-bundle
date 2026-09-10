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
from models.money import Money
from services.money_presentation import project_money, project_transaction_money
from utils.support_locale import SUPPORTED_SUPPORT_LOCALES


@pytest.mark.parametrize("locale", SUPPORTED_SUPPORT_LOCALES)
@pytest.mark.parametrize("currency,amount,display", [
    ("USD", 1299, "USD 12.99"), ("MXN", 101, "MXN 1.01"),
    ("JPY", 123, "JPY 123"), ("BHD", 1234, "BHD 1.234"),
    ("USD", -101, "USD -1.01"),
    ("BHD", 9007199254740991, "BHD 9,007,199,254,740.991"),
])
def test_exact_decimal_facts_without_spoken_scripts(locale, currency, amount, display):
    money = Money(amount_minor=amount, currency_code=currency)
    projected = project_money(money, locale)
    assert projected == {"money": money.model_dump(), "locale": locale, "display_text": display}


def test_cross_currency_billing_is_preserved_without_conversion():
    transaction = Money(amount_minor=19900, currency_code="MXN")
    billing = Money(amount_minor=1053, currency_code="USD")
    result = project_transaction_money(transaction, billing)
    assert result["money"] == transaction.model_dump()
    assert result["billing_money"] == billing.model_dump()
    for locale in SUPPORTED_SUPPORT_LOCALES:
        projected = result["presentations"][locale]
        assert projected["transaction"]["display_text"] == "MXN 199.00"
        assert projected["billing"]["display_text"] == "USD 10.53"
        assert projected["transaction"]["money"] == transaction.model_dump()
        assert projected["billing"]["money"] == billing.model_dump()


def test_no_unvalidated_money_or_implicit_locale_fallback():
    with pytest.raises(TypeError):
        project_money({"amount_minor": 100, "currency_code": "USD"})
    with pytest.raises(ValueError):
        project_money(Money(amount_minor=100, currency_code="USD"), "ja-JP")


def test_reference_summary_keeps_mixed_currency_facts_and_all_consequences():
    from services.fraud_presentation import fraud_proposal_summary
    summary = fraud_proposal_summary(card_last_four="1234", facts=[{
        "merchant_name": "Shop", "money": {"amount_minor": 19900, "currency_code": "MXN"},
        "billing_money": {"amount_minor": 1053, "currency_code": "USD"}}],
        issue_replacement=True, escalate=True)
    for fact in ("MXN 199.00", "USD 10.53", "Shop", "1234", "Block the current card", "replacement virtual card", "specialist review"):
        assert fact in summary
