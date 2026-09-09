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

## Temporary external USD compatibility

`from_legacy_usd` validates legacy input without coercion. `to_legacy_usd`
rejects non-USD values. `money_fields("balance", money, legacy=True)` emits
`balance` plus `balance_cents` only for USD; other currencies omit the legacy
field entirely. The default emits structured Money alone. Endpoint adoption
occurs with each delivering packet; new internal consumers must use Money.

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

## Delivery evidence

- Packet 01: strict Money, metadata, external USD helpers, finite legacy guard,
  offline serialization/OpenAPI tests, and active CI definition delivered.
- Packet 01 validation: 43 offline contract/guard cases passed.
- Packet 02: account constraints, durable journal currency, Money posting inputs,
  currency-specific clearing, transfer retry/denomination checks, additive
  migration, and reconciliation implemented. Combined offline Money/journal/
  SQLite and PostgreSQL migration suite: 67 passed. Existing journal, transfer,
  and credit-service regressions: 28 passed.
- Packets 03–07 and deployed environment qualification: pending.

Deployment qualification will use `evo-genai-workspace`. Preserve its existing
database; use focused checks and additive migration. A full refresh is reserved
for demonstrated necessity. Production staged rollout/rollback certification is
out of scope; financial correctness and immutable-history replay remain in scope.

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
