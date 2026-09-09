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

"""Read-only denomination and balance evidence, including legacy schemas."""

from collections import defaultdict
from sqlalchemy import MetaData, Table, select

SUPPORTED = frozenset({"USD", "MXN", "JPY", "BHD"})


def reconcile_money(connection) -> dict:
    metadata = MetaData()
    def rows(schema, name):
        table = Table(name, metadata, schema=schema, autoload_with=connection)
        return [dict(row) for row in connection.execute(select(table)).mappings()]

    accounts = rows("ledger", "accounts")
    cards = rows("cards", "credit_accounts")
    transactions = rows("ledger", "transactions")
    entries = rows("ledger", "account_ledger")
    by_account = {str(a["id"]): a for a in accounts}
    by_card = {str(a["id"]): a for a in cards}
    by_transaction = {str(t["id"]): t for t in transactions}
    related = defaultdict(list)
    by_tx = defaultdict(list)
    balances = defaultdict(int)
    orphan_entries = []
    for e in entries:
        aid, tid = str(e["account_id"]), str(e["transaction_id"])
        related[aid].append(str(e["entry_id"]))
        by_tx[tid].append(e)
        if aid not in by_account or tid not in by_transaction:
            orphan_entries.append(str(e["entry_id"]))
            continue
        a = by_account[aid]
        sign = 1 if e["entry_type"] == "CREDIT" else -1
        if a["account_type"] == "CREDIT_CARD":
            sign = -sign
        balances[aid] += sign * e["amount_cents"]

    null_accounts, invalid_accounts, mirror_conflicts = [], [], []
    for table, collection in [("ledger.accounts", accounts), ("cards.credit_accounts", cards)]:
        for a in collection:
            item = {"table": table, "id": str(a["id"]), "currency": a["currency"]}
            aid = str(a["id"])
            mirror_ids = [str(m["id"]) for m in accounts if str(m.get("credit_account_id")) == aid]
            item["entry_ids"] = related[aid] if table == "ledger.accounts" else [
                eid for mid in mirror_ids for eid in related[mid]
            ]
            if a["currency"] is None:
                null_accounts.append(item)
            elif a["currency"] not in SUPPORTED:
                invalid_accounts.append(item)
    for a in accounts:
        if a.get("credit_account_id") is not None:
            card = by_card.get(str(a["credit_account_id"]))
            if card is None or (a["currency"] or "USD") != (card["currency"] or "USD"):
                mirror_conflicts.append(str(a["id"]))

    inferred, mixed, unresolved, header_conflicts, unbalanced = {}, [], [], [], []
    for tid, tx in by_transaction.items():
        postings = by_tx[tid]
        currencies = {by_account[str(e["account_id"])]["currency"] or "USD"
                      for e in postings if str(e["account_id"]) in by_account}
        if len(currencies) > 1:
            mixed.append(tid)
        elif len(currencies) != 1 or not currencies <= SUPPORTED:
            unresolved.append(tid)
        else:
            inferred[tid] = next(iter(currencies))
            if tx.get("currency_code") not in (None, inferred[tid]):
                header_conflicts.append(tid)
        if sum(e["amount_cents"] * (1 if e["entry_type"] == "CREDIT" else -1) for e in postings) != 0:
            unbalanced.append(tid)
    differences = [{"account_id": str(a["id"]), "account_type": a["account_type"],
                    "cached_minor": a["cleared_balance_cents"], "journal_minor": balances[str(a["id"])]}
                   for a in accounts if a["cleared_balance_cents"] != balances[str(a["id"])]]
    return {
        "counts": {"accounts": len(accounts), "card_accounts": len(cards),
                   "transactions": len(transactions), "entries": len(entries)},
        "null_accounts": null_accounts, "invalid_accounts": invalid_accounts,
        "mirror_conflicts": mirror_conflicts, "mixed_transactions": mixed,
        "unresolved_transactions": unresolved, "header_conflicts": header_conflicts,
        "orphan_entries": orphan_entries, "unbalanced_transactions": unbalanced,
        "balance_differences": differences, "inferred_transaction_currencies": inferred,
    }


def migration_blockers(report: dict) -> dict:
    return {key: report[key] for key in (
        "invalid_accounts", "mirror_conflicts", "mixed_transactions",
        "unresolved_transactions", "header_conflicts", "orphan_entries", "unbalanced_transactions",
    ) if report[key]}
