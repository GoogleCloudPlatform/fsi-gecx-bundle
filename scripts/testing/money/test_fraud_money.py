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


def test_historical_usd_action_replay_is_centralized_and_does_not_mutate_history():
    from services.fraud_money import normalize_historical_fraud_action
    old = {"voided_amount_cents": 1053, "available_credit_cents": 10000}
    projected = normalize_historical_fraud_action(old, "USD")
    assert projected["voided_amount"] == {"amount_minor": 1053, "currency_code": "USD"}
    assert "voided_amount" not in old
    assert set(projected) == {"voided_amount", "available_credit"}
    with pytest.raises(ValueError, match="non-USD"):
        normalize_historical_fraud_action(old, "MXN")


def test_historical_workflow_replay_projects_nested_money_without_rewriting_outcome():
    from copy import deepcopy
    from services.fraud_money import has_legacy_fraud_amounts, normalize_historical_fraud_workflow
    stored = {"outcome": "PENDING_SPECIALIST_REVIEW", "voided_authorizations": [
        {"authorization_id": "auth", "voided_amount_cents": 1053}],
        "provisional_credits": [{"transaction_id": "posted", "credited_amount_cents": 250}]}
    original = deepcopy(stored)
    assert has_legacy_fraud_amounts(stored)
    replay = normalize_historical_fraud_workflow(stored, "USD")
    assert replay["voided_authorizations"][0] == {
        "authorization_id": "auth", "voided_amount": {"amount_minor": 1053, "currency_code": "USD"}}
    assert replay["provisional_credits"][0]["credited_amount"] == {"amount_minor": 250, "currency_code": "USD"}
    assert not has_legacy_fraud_amounts(replay)
    assert stored == original
    with pytest.raises(ValueError, match="non-USD"):
        normalize_historical_fraud_workflow(stored, "MXN")


@pytest.mark.parametrize("owned", [True, False])
def test_selected_credit_history_uses_owned_account_currency(owned):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from services.credit_card import get_transaction_history_dto
    repo = MagicMock()
    repo.get_account_by_id_for_customer.return_value = (
        SimpleNamespace(id="mxn-account", customer_id="owner", currency="MXN") if owned else None)
    repo.list_authorizations.return_value = []
    repo.list_ledger_entries.return_value = [SimpleNamespace(
        id="posted", amount_cents=-234, description="MXN purchase", posted_at=None, authorization=None)]
    result = get_transaction_history_dto(repo, "owner" if owned else "other", account_id="mxn-account")
    repo.get_account_by_customer.assert_not_called()
    if owned:
        assert result[0]["money"] == {"amount_minor": -234, "currency_code": "MXN"}
        repo.list_ledger_entries.assert_called_once_with("mxn-account")
    else:
        assert result is None
        repo.list_ledger_entries.assert_not_called()


@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize("missing", [False, True])
def test_fraud_triage_rejects_unverifiable_account_before_actions(monkeypatch, replay, missing):
    from services.fraud_alerts import FraudAlertService

    card_repo, alert = repository_and_alert()
    alert.id = "alert"
    if missing:
        card_repo.get_account_by_id.return_value = None
    else:
        card_repo.get_account_by_id.return_value.customer_id = "another-customer"
    monkeypatch.setattr("services.fraud_alerts.CreditCardRepository", lambda db: card_repo)
    db = MagicMock()
    service = FraudAlertService(db)
    service.repo = MagicMock()
    service.repo.get_alert_for_customer.return_value = alert
    service.repo.get_case_action_by_idempotency_key.return_value = (
        SimpleNamespace(status="SUCCEEDED", result_payload={}) if replay else None
    )
    with pytest.raises(ValueError, match="Fraud account ownership cannot be verified"):
        service.triage_fraud_case(
            auth_provider_uid="customer", fraud_alert_id="alert", idempotency_key="same-intent"
        )
    service.repo.get_case_action_by_idempotency_key.assert_not_called()
    service.repo.create_case_action.assert_not_called()
    service.repo.resolve_alert.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()
