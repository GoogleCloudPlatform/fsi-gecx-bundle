# CDC and Apache Iceberg Lakehouse Architecture

This document describes the complementary mutable-table CDC and immutable Iceberg event paths. It deliberately distinguishes BigQuery-native Datastream tables from catalog-native Iceberg tables.

## Deployed mutable-table CDC

```mermaid
flowchart LR
    AlloyDB["AlloyDB PostgreSQL 18<br/>private IP + logical decoding"] --> Publication["datastream_publication<br/>datastream_alloydb_replication_slot"]
    Publication --> PSC["Managed Datastream PSC interface<br/>dedicated consumer subnet"]
    PSC --> Datastream["Datastream private connection"]
    Datastream --> NativeBQ["BigQuery native current-state CDC tables<br/>oltp_cdc dataset"]
    NativeBQ --> Curated["analytics_curated views"]
```

AlloyDB connects to `fsi-gecx-vpc` through Private Service Access. Datastream
uses a separate Private Service Connect interface allocated from the dedicated
`datastream-psc-subnet`. A manual-accept network attachment admits only the
validated Datastream tenant project. Source-range egress rules allow that
subnet to reach only the AlloyDB primary private IP on TCP 5432 and deny its
other egress. No customer-managed proxy process handles database traffic.

Private Service Access and Private Service Connect have different roles here:
Private Service Access retains AlloyDB's managed-service attachment, while the
Datastream PSC interface gives the managed CDC producer a transitive identity
inside the consumer VPC. Terraform owns both consumer-side configurations;
Datastream manages the PSC interface itself.

The `banking_bq_connector` built-in database user owns the Datastream password boundary. The ordered database reconciliation job creates and verifies its replication grant, publication, and AlloyDB-specific logical slot after Alembic completes. Terraform creates a new AlloyDB-specific stream identity rather than retaining a Cloud SQL WAL checkpoint, and the release controller starts that stopped stream only after database and analytics prerequisites pass.

The `oltp_cdc` destination contains BigQuery-native merge-mode replicas, not Apache Iceberg tables and not a retained WAL event history. It exposes the latest source row state plus Datastream metadata. Immutable audit and financial-journal history follows the separate catalog-native Iceberg path below.

### Current-state replica physical design

The demo keeps `oltp_cdc` tables unpartitioned and lets Datastream cluster them by source primary key. This is intentional:

- the tables are small current-state replicas rather than an append-only event archive;
- most dimension and account tables do not have a useful time-partition key;
- BigQuery CDC background apply and runtime merge work cannot use partitions to prune the mutable baseline; and
- the curated layer already applies bounded business timestamps for time-window analysis.

If production-scale query scans justify partitioning later, configure it selectively when Datastream creates new fact tables—for example `cards_posted_transactions.posted_at` and `cards_transaction_authorization.created_at` at daily granularity—and validate CDC cost as well as query cost. Datastream applies partition and clustering configuration only when it creates a destination table, so changing the design requires a controlled table recreation and backfill. See [Partition and cluster BigQuery tables](https://cloud.google.com/datastream/docs/partitioning-and-clustering) and [BigQuery CDC ingestion behavior](https://cloud.google.com/bigquery/docs/change-data-capture).

## Catalog-native Iceberg event architecture

The platform uses two complementary catalog paths:

1. Audit outbox events flow through Pub/Sub into Iceberg managed tables registered in the lakehouse runtime catalog.
2. Existing BigQuery-native mutable CDC tables remain queryable from Spark through BigQuery catalog federation.

```mermaid
flowchart LR
    Outbox["AlloyDB audit outbox"] --> Relay["Bounded relay"] --> PubSub["Pub/Sub"] --> Dataflow["Dataflow Managed Iceberg I/O"] --> Iceberg["Catalog-native Iceberg audit + ledger tables"]
    Mutable["BigQuery-native Datastream CDC tables"] --> Federation["BigQuery catalog federation"]
    Iceberg --> Catalog["Lakehouse runtime catalog"]
    Federation --> Spark["Spark / open-engine analytics"]
    Catalog --> Spark
```

BigQuery queries catalog-native tables with a four-part project/catalog/namespace/table name. Spark connects to the runtime catalog for immutable Iceberg history and uses the Spark BigQuery connector for the mutable BigQuery-native CDC tables in the same session. See [Catalog-Native Iceberg Audit and Financial Ledger](./bigquery_olap_audit_architecture.md) for contracts and operations.

The immutable tables retain the one-minute streaming commit cadence and use catalog-native automatic table management. A six-hour snapshot-history horizon with a minimum of 60 snapshots bounds metadata growth without removing any rows from the current append-only table state. BigLake performs snapshot expiration, orphan-file garbage collection, and small-file compaction asynchronously; the deployment bootstrap reconciles the policy on existing as well as newly created tables.

## Curated analytics contract

The `analytics_curated` views provide stable business-facing names over raw CDC tables. They include enriched posted transactions, spend velocity, international fraud anomalies, and premium travel offer candidates. The view reconciler runs after Datastream activation and fails closed only for required dependencies; optional demo sources may remain deferred until their first backfill.

Operational identities use UUID joins, and authorization-time merchant snapshots remain immutable so historical financial activity does not change when reference data is reseeded.
