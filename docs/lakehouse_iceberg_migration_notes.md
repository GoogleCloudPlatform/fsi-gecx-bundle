# Lakehouse Iceberg Migration Notes

## Current State

The deployed CDC path streams PostgreSQL changes through Datastream into native BigQuery tables in the bronze dataset. The active CDC tables use schema-prefixed names such as `cards_transaction_authorization`, `merchants_merchant_master`, and `kyc_user_credit_profiles`.

The dataset name currently suggests an Iceberg catalog, but the populated CDC tables are native BigQuery tables. Empty legacy BigLake table definitions existed for a few unprefixed table names, but those were not the active Datastream outputs.

## Decision To Make

Before moving CDC to Iceberg managed tables, decide whether the demo values open table format interoperability more than simple current-state BigQuery CDC behavior.

Native BigQuery CDC is simpler for the application and current curated views. Iceberg managed tables provide an open lakehouse story with Parquet data in Cloud Storage, but Datastream writes to Iceberg in append-only mode.

## Implications Of Iceberg

If Datastream writes CDC into Iceberg managed tables, curated views need to treat bronze tables as change logs. Mutable source tables such as merchants, products, support cases, and identity records would need latest-row logic based on Datastream metadata before being used as current-state dimensions.

Append-heavy domains such as card authorizations, posted transactions, ledger entries, fraud model decisions, and scenario outcomes are a more natural fit for append-only lakehouse storage.

## Open Questions

- Should the bronze dataset be renamed when moving away from the current dataset name?
- Should all domains move together, or should append-heavy financial/event domains move first?
- Should raw KYC records be excluded from the lakehouse unless there is a specific governed analytics use case?
- Should curated views read directly from append-only bronze tables, or should there be current-state silver views per mutable domain?
- What partitioning strategy should be used for high-volume event tables?

