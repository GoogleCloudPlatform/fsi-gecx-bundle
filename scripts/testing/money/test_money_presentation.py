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

"""Canonical integer Money and bounded USD compatibility at external edges."""

import pytest

from models.money import Money
from services.money_presentation import project_money, project_transaction_money


@pytest.mark.parametrize("currency,amount,display,english,spanish", [
    ("USD", 149900, "USD 1,499.00", "1499 US dollars and 0 cents", "1499 dólares estadounidenses con 0 centavos"),
    ("MXN", 101, "MXN 1.01", "1 Mexican peso and 1 centavo", "1 peso mexicano con 1 centavo"),
    ("JPY", 123, "JPY 123", "123 Japanese yen", "123 yenes japoneses"),
    ("BHD", 1234, "BHD 1.234", "1 Bahraini dinar and 234 fils", "1 dinar bareiní con 234 fils"),
    ("USD", -101, "USD -1.01", "minus 1 US dollar and 1 cent", "menos 1 dólar estadounidense con 1 centavo"),
    ("BHD", 9007199254740991, "BHD 9,007,199,254,740.991", "9007199254740 Bahraini dinars and 991 fils", "9007199254740 dinares bareiníes con 991 fils"),
])
def test_exact_deterministic_voice_money(currency, amount, display, english, spanish):
    money = Money(amount_minor=amount, currency_code=currency)
    for locale, speech in [("en-US", english), ("es-MX", spanish)]:
        projected = project_money(money, locale)
        assert projected["money"] == money.model_dump()
        assert projected["display_text"] == display
        assert projected["speech_text"] == speech


def test_cross_currency_authorized_billing_is_preserved_without_conversion():
    transaction = Money(amount_minor=19900, currency_code="MXN")
    billing = Money(amount_minor=1053, currency_code="USD")
    result = project_transaction_money(transaction, billing)
    assert result["money"] == transaction.model_dump()
    assert result["billing_money"] == billing.model_dump()
    assert result["presentations"]["es-MX"]["transaction"]["speech_text"] == "199 pesos mexicanos con 0 centavos"
    assert result["presentations"]["es-MX"]["billing"]["speech_text"] == "10 dólares estadounidenses con 53 centavos"


def test_no_unvalidated_money_or_implicit_language_fallback():
    with pytest.raises(TypeError):
        project_money({"amount_minor": 100, "currency_code": "USD"})
    with pytest.raises(ValueError):
        project_money(Money(amount_minor=100, currency_code="USD"), "fr-FR")
