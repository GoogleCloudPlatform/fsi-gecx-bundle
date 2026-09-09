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

"""Deterministic presentation of validated banking Money facts."""

from models.money import Money
from utils.support_locale import SUPPORTED_SUPPORT_LOCALES


SUPPORTED_VOICE_LOCALES = SUPPORTED_SUPPORT_LOCALES
# Both code and full currency name are intentional: language does not select
# denomination, and a bare dollar sign is ambiguous in the reference journey.
_NAMES = {
    "en-US": {
        "USD": ("US dollar", "US dollars", "cent", "cents"),
        "MXN": ("Mexican peso", "Mexican pesos", "centavo", "centavos"),
        "JPY": ("Japanese yen", "Japanese yen", "", ""),
        "BHD": ("Bahraini dinar", "Bahraini dinars", "fils", "fils"),
    },
    "es-MX": {
        "USD": ("dólar estadounidense", "dólares estadounidenses", "centavo", "centavos"),
        "MXN": ("peso mexicano", "pesos mexicanos", "centavo", "centavos"),
        "JPY": ("yen japonés", "yenes japoneses", "", ""),
        "BHD": ("dinar bareiní", "dinares bareiníes", "fils", "fils"),
    },
}


# Regional variants share explicit banking terminology; neither locale nor
# language can change the denomination of a validated Money value.
_NAMES["es-ES"] = _NAMES["es-US"] = _NAMES["es-MX"]
_NAMES["fr-FR"] = _NAMES["fr-CA"] = {
    "USD": ("dollar américain", "dollars américains", "cent", "cents"),
    "MXN": ("peso mexicain", "pesos mexicains", "centavo", "centavos"),
    "JPY": ("yen japonais", "yens japonais", "", ""),
    "BHD": ("dinar bahreïni", "dinars bahreïnis", "fils", "fils"),
}
_NAMES["de-DE"] = {
    "USD": ("US-Dollar", "US-Dollar", "Cent", "Cent"),
    "MXN": ("mexikanischer Peso", "mexikanische Pesos", "Centavo", "Centavos"),
    "JPY": ("japanischer Yen", "japanische Yen", "", ""),
    "BHD": ("Bahrain-Dinar", "Bahrain-Dinar", "Fils", "Fils"),
}
_NAMES["pt-BR"] = {
    "USD": ("dólar americano", "dólares americanos", "centavo", "centavos"),
    "MXN": ("peso mexicano", "pesos mexicanos", "centavo", "centavos"),
    "JPY": ("iene japonês", "ienes japoneses", "", ""),
    "BHD": ("dinar bareinita", "dinares bareinitas", "fils", "fils"),
}
_CONJUNCTION = {"en": "and", "es": "con", "fr": "et", "de": "und", "pt": "e"}
_MINUS = {"en": "minus", "es": "menos", "fr": "moins", "de": "minus", "pt": "menos"}


def project_money(money: Money, locale: str = "en-US") -> dict:
    """Lossless display/speech facts. No float, locale inference, or FX."""
    if not isinstance(money, Money):
        raise TypeError("A validated Money value is required")
    if locale not in SUPPORTED_VOICE_LOCALES:
        raise ValueError("Unsupported voice presentation locale")
    whole, fraction = divmod(abs(money.amount_minor), 10 ** money.exponent)
    digits = f"{whole:,}"
    if money.exponent:
        digits += f".{fraction:0{money.exponent}d}"
    singular, plural, minor_singular, minor_plural = _NAMES[locale][money.currency_code]
    speech = f"{whole} {singular if whole == 1 else plural}"
    if money.exponent:
        conjunction = _CONJUNCTION[locale.split("-")[0]]
        speech += f" {conjunction} {fraction} {minor_singular if fraction == 1 else minor_plural}"
    if money.amount_minor < 0:
        digits = "-" + digits
        speech = (_MINUS[locale.split("-")[0]] + " ") + speech
    return {
        "money": money.model_dump(),
        "locale": locale,
        "display_text": f"{money.currency_code} {digits}",
        "speech_text": speech,
    }


def project_transaction_money(transaction: Money, billing: Money) -> dict:
    """Keep original purchase and the already-authorized billing fact distinct."""
    return {
        "money": transaction.model_dump(),
        "billing_money": billing.model_dump(),
        "presentations": {
            locale: {
                "transaction": project_money(transaction, locale),
                "billing": project_money(billing, locale),
            }
            for locale in SUPPORTED_VOICE_LOCALES
        },
    }
