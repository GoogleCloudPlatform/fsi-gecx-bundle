# Canonical Money foundation

The banking service simulates core, issuer, and payment authorities for an
illustrative demo. Money is the boundary contract; it does not implement FX.

## Money v1

```json
{"amount_minor": 149900, "currency_code": "USD"}
```

`models.money.Money` is immutable and rejects unknown fields, non-integer
amounts (including booleans, floats and numeric strings), unsupported codes,
and values outside `[-9007199254740991, 9007199254740991]`. This is the common
lossless PostgreSQL BIGINT / browser integer range. Currency is required, never
inferred from locale, market, merchant location, or language.

Currency metadata: USD/MXN have exponent 2, JPY 0, BHD 3. USD and MXN are the
live demo currencies; JPY and BHD prevent two-decimal assumptions in tests.
Negative Money is valid when its enclosing contract uses signs. Journal entries
require positive amounts with a separate DEBIT/CREDIT direction.

## Canonical external contracts

Delivered payment, account summary, transaction history and fraud-result
boundaries expose structured Money only. Bill payment requires `money` and an
`Idempotency-Key`; legacy amount fields are rejected. `money_fields` emits only
the named Money object, including for USD. Deposit history carries unsigned
entry Money with explicit DEBIT/CREDIT direction and a Money running balance.

`from_legacy_usd` is retained solely for immutable historical USD fraud results.
That reader returns canonical Money without rewriting stored payloads. Physical
ledger and Iceberg storage columns and the centralized financial-event v1 reader
remain intact; they are not active request or response aliases.

The standalone OpenAPI contract test checks integer bounds, required fields,
currency enum, and HTTP round trips against a minimal FastAPI app. It does not
add a production endpoint or initialize the banking application.

## Legacy usage review

`scripts/legacy_money_allowlist.json` records source-line fingerprints, symbols,
owners, and dispositions for existing legacy usage. The guard covers tracked
and untracked code in application, generator, voice, deployment, and lakehouse
surfaces, including fixtures and historical migrations. It rejects additions,
changed legacy-bearing source lines, and increased duplicate counts. Deletions
are allowed; prune obsolete fingerprints as each packet lands. Never regenerate
the whole baseline to conceal newly introduced usage. Existing persistence
column names are not permission to expose new cents-based contracts.

Run `./scripts/test_money_foundation.sh`. The active Money Foundation workflow
runs this entry point on PRs and main updates. Contract tests block network
connections and avoid backend startup and cloud credentials.

## Qualification records

Implementation plans, review notes and deployment qualification evidence live
in the FSI solutions workbench under the active
`internationalization-and-money-foundation` work item.

## Currency migration and reconciliation

Migration `d8e2f6a910bc` first archives `MONEY_RECONCILIATION_REPORT` (default
`money-reconciliation-before.json`) before changing data. It stops for invalid
currencies, card mirror conflicts, mixed/unresolved transaction currencies,
orphans, or unbalanced entries. Only reported null denominations become USD.
Transaction headers inherit the unambiguous account currency; existing journal
entries and outbox payloads remain unchanged.

For a read-only preflight, run from banking-service:

```sh
uv run python scripts/reconcile_money.py --output /tmp/money-before.json
```

Use the configured `DATABASE_URL`/IAM connector for the selected environment.
Reports contain account/entry identifiers and cached-versus-journal differences.
Seeded demo balances may have opening offsets; report those differences and
compare before/after rather than inventing corrective financial postings.
The migration does not reconcile caches by rewriting history or reseeding.

For local PostgreSQL migration checks, set `TEST_MONEY_DATABASE_URL` to a
**disposable** database whose name ends in `_money_test`, then run the Money
entry point. Those tests create/drop fixture tables only in that test database.
CI supplies PostgreSQL 16; local validation also exercised PostgreSQL 14.
The additive migration refuses downgrade; use fix-forward or the explicit
existing demo reset path only if necessary.

## Bill-payment authority and retry contract

`POST /v1/credit-card/pay` (and existing route aliases) accepts account UUIDs and
`money`. Structured requests require `Idempotency-Key` (1–128 nonblank characters).
Its durable identity is scoped to the authenticated user and operation. Reusing
it with a changed account, amount, or denomination returns 409; exact replay
returns the original posted result and original resulting balances, even after
later payments. It does not post another journal, statement, or audit record.

The simulator locks deposit, card, and existing journal mirror rows before
mutation. Journal, balances, statement, audit, and response persistence commit
atomically. Insufficient funds, overpayment and denomination mismatch return
422; contention returns 409 with same-key retry guidance. Malformed or unsupported
currency returns 400. Ownership and source account type are validated.

All payment requests require a stable key and structured Money. Summaries and
payment responses expose no legacy cents fields for any currency. Checked-in
payment/UI consumers use Money.
Simulation auto-paydown returns structured target/paid/remaining amounts.

The browser parses decimal strings with integer arithmetic, uses currency
metadata for precision, and retains payment intent keys across retries.
Dashboard totals group currencies separately. Active locale controls display
and copy while currency metadata controls amount precision.

Locale changes presentation only; it never changes the denomination or payment
intent. English is the UI-copy fallback when translated copy is unavailable.
Credit history is scoped to the selected account and authenticated customer.

## Event and analytical Money

New `FINANCIAL_TRANSACTION_POSTED` events use schema version 2, top-level
`currency_code`, and entry `money` objects. The Dataflow reader accepts v1 and
v2 together, rejects conflicting event identities, duplicate entry IDs,
malformed integers, unsafe v2 amounts, currency mismatches and imbalance.
Transport redelivery preserves immutable IDs; logical views deduplicate audit
records by event ID and postings by entry ID.

The existing physical Iceberg `amount_cents`/`currency` columns remain intact
for snapshot compatibility. Their logical aliases are `amount_minor` and
`currency_code`. All selected active queries use those normalized columns.
The one v1 event adapter is the Java ingestion reader; historical payloads are
never rewritten. Non-journal historical side events lacking a denomination
retain their raw payload but have no inferred normalized amount.

Posted-card analytics exposes exact NUMERIC unit projections and integer
minor-unit facts. Customer balances are an array grouped by denomination,
which prevents a customer with USD and MXN accounts from silently combining
those balances. Selected views expose no legacy dollar aliases. The data agent is
restricted to normalized sources for monetary questions; unrelated curated
views remain available for non-monetary facts only.


## Spanish fraud voice contracts

Fraud context resolves account-scoped authoritative transaction and billing
Money; an ambiguous historical alert snapshot cannot select currency or override
the posting. English/Spanish display and speech use integer arithmetic. Proposal
Money and both deterministic presentations are frozen inside its payload
fingerprint. A language change retains the opaque proposal and clears prior
presentation/confirmation evidence. An uncertain commit must finish recovery
before the language changes. Live reconnect uses a fresh speech configuration
without changing the support session or currency.

Available credit sums validated billing Money for PENDING and FLAGGED holds.
A flagged MXN purchase billed in USD is released by its USD billed amount;
mismatched billing currency rolls back. Authorization releases, provisional
credits, alert snapshots, secure-message amounts and aggregate audit facts use
currency-aware Money. One reader normalizes immutable pre-Money USD action
results without rewriting stored payloads.

Explicit Spanish runtime language rejection persists English locale and
invalidated proposal evidence before reconnecting. It preserves Money and opaque
proposal identity, surfaces reviewed fallback wording, and requires another
presentation and confirmation. Unrelated runtime errors and uncertain commits
do not trigger this fallback.

Both standalone reconciliation scripts use a consistent PostgreSQL snapshot.
The additive migration locks its four source tables against concurrent writes
and uses a set-based denomination backfill. Reconciliation must preserve
existing entries and immutable events; it does not reset the demo database.
