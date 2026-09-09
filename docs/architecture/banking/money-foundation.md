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

## Delivery evidence

The current deployed qualification record for Packets 01–06 is
maintained in the FSI solutions workbench under the active
`internationalization-and-money-foundation` work item.

- Packet 01: strict Money, metadata, external USD helpers, finite legacy guard,
  offline serialization/OpenAPI tests, and active CI definition delivered.
- Packet 01 validation: 43 offline contract/guard cases passed.
- Packet 02: account constraints, durable journal currency, Money posting inputs,
  currency-specific clearing, transfer retry/denomination checks, additive
  migration, and reconciliation implemented. Combined offline Money/journal/
  SQLite and PostgreSQL migration suite: 67 passed. Existing journal, transfer,
  and credit-service regressions: 28 passed.
- Packet 03: Money account summaries, atomic same-currency bill payment,
  durable retries, simulation caller migration, and baseline UI contract
  migration implemented. Combined offline suite: 87 passed, including real
  PostgreSQL lock contention and concurrent duplicate/distinct requests.
  Existing backend regressions: 42 passed. UI tests: 26 passed; build passed.
- Packet 03 generator auto-paydown regressions: 2 passed.
- Packet 04: active presentation locale, English/Spanish payment copy, exact
  currency formatting, and visual qualification implemented. UI suite: 31
  passed, including en-US/USD, es-MX/USD, es-MX/MXN, ja-JP/JPY and ar-BH/BHD.
  UI build and focused ESLint passed.
- Packet 05 implementation: financial event v2, strict versioned Java reader,
  immutable raw history and physical Iceberg schema, normalized logical views,
  and per-currency customer balances/spend metrics. Active CI includes parser
  replay and logical-view regressions. 87 Money tests, 48 backend regressions,
  and 8 Java parser tests passed. BigQuery dry runs of both curated views passed
  in `evo-genai-workspace` on 2026-09-08. Integrated CDC/outbox/Iceberg runtime
  reconciliation remains pending; dry runs do not establish runtime qualification.
- Packets 06–07 and deployed environment qualification: pending.

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
Dashboard totals group currencies separately. Packet 04 adds active-locale
presentation and visual qualification on top of this contract migration.

## Browser qualification (2026-09-08)

The dev-only `banking-ui/tests/fixtures/money.html?currency=MXN` fixture mounts
actual BillPayModal and Money utilities without Firebase. Playwright used
intercepted fixture HTTP responses; these browser checks are separate from the
real PostgreSQL posting tests and are not deployed-environment qualification.

- Inspected 390×844 Spanish and 1440×1000 English layouts. Balance text has its
  own visible line so long account names cannot clip consequential amounts.
- Rejected `12.345` for MXN before HTTP submission. Switching language updates
  the validation message and display amounts without changing decimal input.
- Submitted `12.34` as `{amount_minor:1234,currency_code:"MXN"}`. After a
  fixture 409, switched Spanish to English and retried. Both captured requests
  had identical account IDs, Money and idempotency keys.
- A posted fixture response refreshed deposit/card balances to MX$87.66 and
  MX$37.66. No compatibility fields were sent by the browser.
- Screenshots are local artifacts under `output/playwright/`:
  `money-es-mxn-mobile.png` and `money-en-mxn-desktop.png`.

Locale only changes presentation. English is the UI-copy fallback for Japanese
and Arabic projection fixtures. Spanish consequential content has received the
user-authorized assistant review recorded below; live multilingual qualification
remains required.


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
those balances. Legacy dollar aliases cover USD alone. The data agent is
restricted to normalized sources for monetary questions; unrelated curated
views remain available for non-monetary facts only.


## Environment progress (2026-09-08)

Release `101adbf`, project `evo-genai-workspace`: the seven logical Iceberg views
and both selected curated views were reconciled. The read returned 2,238,061
audit events (all distinct), 1,593,180 ledger entries (all distinct), and zero
imbalanced transaction/currency groups. This verifies retained history through
the new views, not yet v2 posting/CDC end-to-end reconciliation.

Dataflow build `ee9074e1-2e2f-4bb5-85c0-bbdd492d70ca` succeeded. Replacement job
`2026-09-08_18_03_03-5377683810347333006` reached RUNNING and replaced
`2026-07-31_14_03_15-14773413879608518577`; exactly one matching job was running.
No database refresh, migration or banking-service deployment has occurred yet.

## Spanish voice increment

Fraud context now resolves account-scoped authoritative transaction and billing
Money; an ambiguous historical alert snapshot cannot select currency or override
the posting. English/Spanish display and speech use integer arithmetic. Proposal
Money and both deterministic presentations are frozen inside its payload
fingerprint. A language change retains the opaque proposal and clears prior
presentation/confirmation evidence. An uncertain commit must finish recovery
before the language changes. Live reconnect uses a fresh speech configuration
without changing the support session or currency.

The user explicitly delegated Spanish content review to the assistant on
2026-09-08. The review record in the FSI solutions workbench documents that this
is assistant review, not human/native-speaker certification. This user direction
supersedes the plan's human-review prerequisite; live qualification is still
required. The shared content resource records review method and date.

Incremental checks: 104 focused Money tests (including PostgreSQL), 105 backend
regressions, and 196 ADK tests pass after Live stream restart wiring. UI tests
and build pass. Final whole-scope verification remains
pending. Remaining Packet 06 work includes selected result/history consumers,
Spanish trajectory fixtures, UI inspection, deployed USD/MXN and Spanish live
qualification with transcript/tool/proposal/final-state evidence. Packet 07
compatibility removal is still pending qualification.


The next fraud increment fixes available-credit recalculation to sum validated
billing Money for PENDING and FLAGGED holds. A flagged MXN purchase billed in
USD is released by its USD billed amount; mismatched billing currency rolls
back. Fraud authorization releases, provisional credits, alert snapshots,
secure-message amounts and aggregate audit facts now carry/use currency-aware
Money. External projections now contain only Money. One reader normalizes
immutable pre-Money USD action results without rewriting their stored payloads.
Checks after this increment: 105 focused Money tests and 108 backend regressions
passed, including cross-currency billed holds and MXN provisional credits.

### Qualification build and MCP fixture checks

Cloud Build `c0f97904-9e8e-417e-acb2-a7f61b2bca29` succeeded in
`evo-genai-workspace` for source `f8bec0b394fcffc2a9a464272602f0ab2f6e7883`,
building banking-service, banking-ui and credit-support-agent images. This is
build evidence only; database migration and live qualification remain pending.

The additional MCP/simulation regression run passed 35 checks and exposed four
fraud fixtures that omitted currency facts. Replacing those mocks with persisted
USD authorizations made all four targeted reruns pass. Their physical storage
columns are explicitly covered by the reviewed legacy allowlist.

### Snapshot reconciliation and runtime fallback

The first read-only deployed preflight (`money-foundation-preflight-vz68t`)
archived 6,063 ledger accounts, 2,021 card accounts, 195,082 transaction headers
and 390,166 entries. It reported two apparent orphan entries while demo traffic
continued. Because the old preflight used separate READ COMMITTED reads, that
report does not establish an actual orphan: a transaction can commit between
header and entry scans. A second execution, `money-foundation-preflight-g8tt9`,
uses the same built image with an explicit REPEATABLE READ engine override and
archives to `money-foundation/preflight-f8bec0b-snapshot-20260909.json.gz` in the
interaction-artifacts bucket. Its result is pending. No migration or reset has
run and writes remain enabled.

Both standalone reconciliation scripts now use a consistent PostgreSQL snapshot.
The migration locks its four source tables against concurrent writes and uses a
set-based denomination backfill. All 20 actual migration checks pass on SQLite
and PostgreSQL, including preservation of USD, MXN, JPY and BHD records.

Explicit Spanish runtime language rejection now persists English locale and
invalidated proposal evidence before reconnecting. It preserves Money and opaque
proposal identity, surfaces reviewed fallback wording, and requires another
presentation and confirmation. Unrelated runtime errors and uncertain commits do
not trigger this fallback. The full ADK suite passes (201 tests). CES fake fraud
responses now include canonical purchase/billing Money and deterministic
projections; all 27 CES callback checks pass and are included in Money CI.
