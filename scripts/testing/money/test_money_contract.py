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

"""Offline public contract tests; deliberately independent of backend startup."""

from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "banking-service"))
sys.path.insert(0, str(ROOT / "scripts"))
from models.money import (  # noqa: E402
    CURRENCY_EXPONENTS, MAX_MINOR, Money, from_legacy_usd, money_fields,
)
from check_legacy_money import inventory, violations  # noqa: E402


@pytest.mark.parametrize("code,exponent", [("USD", 2), ("MXN", 2), ("JPY", 0), ("BHD", 3)])
@pytest.mark.parametrize("amount", [-MAX_MINOR, -1234, 0, 1234, MAX_MINOR])
def test_lossless_roundtrip(code, exponent, amount):
    value = Money(amount_minor=amount, currency_code=code)
    assert Money.model_validate_json(value.model_dump_json()) == value
    assert value.exponent == exponent == CURRENCY_EXPONENTS[code]


@pytest.mark.parametrize("amount", [True, False, 1.0, 1.5, "123", None, MAX_MINOR + 1, -MAX_MINOR - 1])
def test_no_coercion_or_overflow(amount):
    with pytest.raises(ValidationError):
        Money(amount_minor=amount, currency_code="USD")


@pytest.mark.parametrize("code", ["usd", "Usd", "EUR", "US", " USD", "USD ", None, 123])
def test_supported_canonical_codes_only(code):
    with pytest.raises(ValidationError):
        Money(amount_minor=123, currency_code=code)


def test_required_currency_extra_fields_and_immutability():
    with pytest.raises(ValidationError):
        Money(amount_minor=123)
    with pytest.raises(ValidationError):
        Money(amount_minor=123, currency_code="USD", amount_cents=123)
    value = from_legacy_usd(123)
    with pytest.raises(ValidationError):
        value.amount_minor = 456
    with pytest.raises(TypeError):
        CURRENCY_EXPONENTS["USD"] = 3


def test_historical_usd_reader_is_strict():
    assert from_legacy_usd(125) == Money(amount_minor=125, currency_code="USD")
    with pytest.raises(ValidationError):
        from_legacy_usd(1.25)


@pytest.mark.parametrize("code", ["USD", "MXN", "JPY", "BHD"])
def test_named_projection_is_money_only(code):
    value = Money(amount_minor=125, currency_code=code)
    assert money_fields("balance", value) == {"balance": value.model_dump()}


def test_openapi_and_http_serialization():
    app = FastAPI()

    @app.post("/money", response_model=Money)
    def echo(value: Money):
        return value

    schema = app.openapi()["components"]["schemas"]["Money"]
    assert set(schema["required"]) == {"amount_minor", "currency_code"}
    assert schema["properties"]["amount_minor"]["type"] == "integer"
    assert schema["properties"]["amount_minor"]["maximum"] == MAX_MINOR
    assert schema["properties"]["currency_code"]["enum"] == list(CURRENCY_EXPONENTS)
    with TestClient(app) as client:
        for example in schema["examples"]:
            response = client.post("/money", json=example)
            assert response.status_code == 200
            assert response.json() == example
        assert client.post("/money", json={"amount_minor": 1.5, "currency_code": "USD"}).status_code == 422


def test_guard_detects_new_changed_and_duplicate_usage(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    source = tmp_path / "banking-service" / "example.py"
    source.parent.mkdir()
    source.write_text("amount_cents = 1\n")
    actual = inventory(tmp_path)
    assert violations(actual, {})
    baseline = {p: dict(e, owner="packet-03", rationale="temporary USD ingress") for p, e in actual.items()}
    assert not violations(actual, baseline)
    source.write_text("amount_cents = 2\n")
    assert violations(inventory(tmp_path), baseline)
    source.write_text("amount_cents = 1\namount_cents = 1\n")
    assert violations(inventory(tmp_path), baseline)
    source.write_text("amount_minor = 1\n")
    assert not violations(inventory(tmp_path), baseline)


def test_browser_currency_metadata_matches_service():
    import re
    source = (ROOT / "banking-ui/src/utils/money.js").read_text()
    table = re.search(r"currencyExponents = Object.freeze\(\{([^}]+)\}", source).group(1)
    browser = {code: int(exponent) for code, exponent in re.findall(r"([A-Z]{3}): (\d+)", table)}
    assert browser == dict(CURRENCY_EXPONENTS)
