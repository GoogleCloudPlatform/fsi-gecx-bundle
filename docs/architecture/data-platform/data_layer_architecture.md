# Enterprise Data Layer Architecture

Nova Horizon separates transactional processing in AlloyDB for PostgreSQL from analytical processing in BigQuery. AlloyDB is the only active OLTP source in deployed environments.

```mermaid
flowchart LR
    Services["Cloud Run services and jobs"] -->|"private VPC + IAM database auth + TLS"| AlloyDB["AlloyDB PostgreSQL 18<br/>banking-data / banking-primary"]
    AlloyDB -->|"logical decoding"| Bridge["Datastream TCP bridge"]
    Bridge --> Datastream["Datastream CDC"]
    Datastream --> BigQuery["BigQuery CDC and curated analytics"]
    AlloyDB --> Federation["BigQuery AlloyDB federation"]
    Outbox["audit.audit_outbox"] --> PubSub["Pub/Sub audit-events"]
    PubSub --> Audit["BigQuery compliance_audit"]
```

## OLTP ownership

The `banking` database is divided into bounded schemas: `identity`, `kyc`, `ledger`, `cards`, `operations`, `origination`, `audit`, `admin`, `catalog`, `ref_data`, `merchants`, and `voice_support_sessions`. AlloyDB provides managed PostgreSQL, automated backups and point-in-time recovery, query insights, IAM-integrated authentication, and environment-specific availability:

- Developer environments use a cost-conscious zonal primary.
- `fsi-demo-1841` uses a regional high-availability primary.
- All application traffic uses private IP; there is no public database endpoint.
- Runtime services authenticate as AlloyDB IAM database users with short-lived tokens and required TLS.

## Database release contract

Database deployment has three explicit owners:

1. Terraform owns the AlloyDB cluster and instance, network, IAM bindings, database users, secrets, Cloud Run jobs, and Datastream resources.
2. Alembic owns schemas, tables, indexes, constraints, and versioned application DDL. The consolidated baseline revision is `2ea57c78ba89`.
3. The database lifecycle jobs own cluster roles, group memberships, database creation, object ownership, grants, default privileges, immutable-ledger revocations, publication, replication slot, and invariant verification.

The ordered release is:

```mermaid
flowchart LR
    Build["Resolve immutable image digests"] --> TF["Environment-specific Terraform plan/apply"]
    TF --> Bootstrap["banking-db-bootstrap"]
    Bootstrap --> Migrate["banking-db-migrate"]
    Migrate --> Reconcile["banking-db-reconcile"]
    Reconcile --> Deploy["Deploy services by digest"]
    Deploy --> Seed["banking-db-reset"]
    Seed --> CDC["Federation + Datastream activation"]
    CDC --> Smoke["Service and analytics smoke tests"]
    Smoke --> Manifest["Immutable release manifest"]
```

Application services never create roles or repair grants, and they do not own schema objects. Bootstrap and reconciliation are idempotent and fail closed when a Terraform-managed principal or database invariant is missing.

## Analytics paths

- Mutable operational tables flow through PostgreSQL logical decoding and Datastream into BigQuery CDC tables.
- Analysts can query the live `banking` database through the BigQuery `banking-postgres-connection`, implemented as a native AlloyDB connector configuration.
- Transactional outbox events flow through Pub/Sub into `compliance_audit` independently of mutable-table CDC.
- AlloyDB Dataplex integration publishes operational metadata into Universal Catalog; the application-specific fraud guidance catalog remains managed by its dedicated sync job.

See [Apache Iceberg CDC Data Lakehouse](./apache_iceberg_cdc_datalake_architecture.md), [BigQuery OLAP Audit Architecture](./bigquery_olap_audit_architecture.md), and [Real Time Analytics Agent](./real_time_analytics_agent_architecture.md).
