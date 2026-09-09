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
