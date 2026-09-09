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

"""Resolve fraud Money from authoritative, account-scoped posting records."""

from models.money import Money
from services.money_presentation import project_transaction_money


def fraud_money_facts(repository, alert) -> list[dict]:
    account = repository.get_account_by_id(str(alert.credit_account_id))
    if account is None or str(account.customer_id) != str(alert.customer_id):
        raise ValueError("Fraud account ownership cannot be verified")
    facts = []
    for item in alert.suspicious_transactions or []:
        authorization = None
        transaction = None
        if item.get("transaction_id"):
            transaction = repository.get_ledger_entry_by_id_for_account(
                str(item["transaction_id"]), str(account.id))
            if transaction is None:
                raise ValueError("Fraud posting is unavailable for this account")
            authorization = transaction.authorization
        elif item.get("authorization_id"):
            authorization = repository.get_authorization_by_id_for_account(
                str(item["authorization_id"]), str(account.id))
            if authorization is None:
                raise ValueError("Fraud authorization is unavailable for this account")
        else:
            raise ValueError("Fraud monetary facts require an authoritative transaction reference")
        if transaction is not None:
            billing = Money(amount_minor=abs(transaction.amount_cents), currency_code=account.currency)
        else:
            billing = Money(amount_minor=authorization.billing_amount_cents,
                            currency_code=authorization.billing_currency)
        if billing.currency_code != account.currency:
            raise ValueError("Fraud billing currency does not match the account")
        original = (Money(amount_minor=authorization.transaction_amount_cents,
                          currency_code=authorization.transaction_currency)
                    if authorization is not None else billing)
        # Never expose or reinterpret a historical alert's ambiguous cents snapshot.
        fact = {key: item.get(key) for key in (
            "authorization_id", "transaction_id", "merchant_name",
            "merchant_category_code", "card_network", "created_at", "pending", "source")}
        fact.update(project_transaction_money(original, billing))
        facts.append(fact)
    return facts


def authorization_money_facts(authorization) -> dict:
    return project_transaction_money(
        Money(amount_minor=authorization.transaction_amount_cents,
              currency_code=authorization.transaction_currency),
        Money(amount_minor=authorization.billing_amount_cents,
              currency_code=authorization.billing_currency))


def normalize_historical_fraud_action(result: dict, currency_code: str) -> dict:
    """Read immutable pre-Money USD action results at one compatibility edge."""
    from models.money import from_legacy_usd, money_fields
    normalized = dict(result)
    for field in ("voided_amount", "credited_amount", "available_credit", "cleared_balance"):
        legacy_field = field + "_cents"
        if field in result:
            money = Money.model_validate(result[field])
        elif legacy_field in result:
            if currency_code != "USD":
                raise ValueError("Historical USD fraud result cannot be used for a non-USD account")
            money = from_legacy_usd(result[legacy_field])
        else:
            continue
        if money.currency_code != currency_code:
            raise ValueError("Fraud result denomination does not match the account")
        normalized.pop(legacy_field, None)
        normalized.update(money_fields(field, money))
    return normalized


def has_legacy_fraud_amounts(result: dict) -> bool:
    return any(key.endswith("_cents")
               for field in ("voided_authorizations", "provisional_credits")
               for item in result.get(field, []) for key in item)


def normalize_historical_fraud_workflow(result: dict, currency_code: str) -> dict:
    """Project stored workflow outcomes without altering their immutable payloads."""
    normalized = dict(result)
    for field in ("voided_authorizations", "provisional_credits"):
        if field in result:
            normalized[field] = [normalize_historical_fraud_action(item, currency_code)
                                 for item in result[field]]
    return normalized
