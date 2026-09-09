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

from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from services.fraud_money import fraud_money_facts


def repository_and_alert(currency="USD", purchase_currency="MXN"):
    repo = MagicMock()
    repo.get_account_by_id.return_value = SimpleNamespace(id="account", customer_id="customer", currency=currency)
    repo.get_authorization_by_id_for_account.return_value = SimpleNamespace(
        transaction_amount_cents=19900, transaction_currency=purchase_currency,
        billing_amount_cents=1053, billing_currency=currency)
    alert = SimpleNamespace(credit_account_id="account", customer_id="customer", suspicious_transactions=[
        {"authorization_id": "auth", "merchant_name": "Merchant", "amount_cents": 999999}])
    return repo, alert


@pytest.mark.parametrize("currency", ["USD", "MXN", "JPY", "BHD"])
def test_fraud_facts_use_scoped_authoritative_source_not_legacy_snapshot(currency):
    repo, alert = repository_and_alert(currency)
    fact, = fraud_money_facts(repo, alert)
    assert fact["money"] == {"amount_minor": 19900, "currency_code": "MXN"}
    assert fact["billing_money"] == {"amount_minor": 1053, "currency_code": currency}
    assert "amount_cents" not in fact
    repo.get_authorization_by_id_for_account.assert_called_once_with("auth", "account")


def test_zero_billing_never_falls_back_to_foreign_purchase_amount():
    repo, alert = repository_and_alert()
    repo.get_authorization_by_id_for_account.return_value.billing_amount_cents = 0
    assert fraud_money_facts(repo, alert)[0]["billing_money"]["amount_minor"] == 0


@pytest.mark.parametrize("problem", ["ownership", "missing_authorization", "missing_reference", "billing_currency"])
def test_unverifiable_or_mismatched_fraud_money_is_rejected(problem):
    repo, alert = repository_and_alert()
    if problem == "ownership": repo.get_account_by_id.return_value.customer_id = "another"
    elif problem == "missing_authorization": repo.get_authorization_by_id_for_account.return_value = None
    elif problem == "missing_reference": alert.suspicious_transactions = [{"amount_cents": 123}]
    else: repo.get_authorization_by_id_for_account.return_value.billing_currency = "MXN"
    with pytest.raises(ValueError):
        fraud_money_facts(repo, alert)
