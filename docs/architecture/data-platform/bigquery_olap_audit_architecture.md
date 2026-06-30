# 🏛️ BigQuery OLAP Audit & Compliance Architecture Blueprint

This document specifies the Enterprise OLAP Data Warehousing and Compliance Auditing architecture for the Nova Horizon Banking Platform. It defines our domain-segmented BigQuery auditing strategy, mandatory partitioning guardrails, native JSON search indexing, and FSI regulatory compliance rules.

---

## 🌐 1. Executive Summary & OLAP Topology

To achieve FSI regulatory compliance across Equal Credit Opportunity (ECOA), Anti-Money Laundering (AML), and Data Privacy (GDPR/CCPA) laws, our platform separates live transactional OLTP processing (Cloud SQL PostgreSQL) from immutable analytical warehousing (Google Cloud BigQuery).

Rather than dumping disparate system events into a single monolithic audit table, we establish a dedicated **`compliance_audit`** dataset in BigQuery segmented by Bounded Context workflows:

```mermaid
graph TD
    subgraph OLTP ["OLTP - Cloud SQL PostgreSQL"]
        Outbox["audit.audit_outbox"]
    end

    subgraph OLAP ["OLAP - BigQuery compliance_audit Dataset"]
        ORIG["origination_audit_log (Partitioned: DAY | Clustered: application_id, event_type | Retain: 10 Years ECOA)"]
        FIN["financial_ledger_audit_log (Partitioned: MONTH | Clustered: account_id, event_type | Retain: 7 Years SOX/AML Immutable)"]
        ID["identity_access_audit_log (Partitioned: DAY | Clustered: user_id, event_type | Retain: 3 Years GDPR/CCPA)"]
    end

    Outbox -->|"PubSub / Storage Write API"| ORIG & FIN & ID
```

---

## 🏛️ 2. Domain-Segmented Audit Tables

### A. `origination_audit_log` (Underwriting & Loan Origination)
* **Regulatory Regime**: Equal Credit Opportunity Act (ECOA) and Fannie Mae guidelines. Requires preserving document extraction results and human loan officer override decisions for up to 10 years to prove fair lending practices.
* **Core Events**: `APPLICATION_CREATED`, `ARTIFACT_UPLOADED`, `DOCUMENT_EXTRACTION_COMPLETED`, `UNDERWRITING_OVERRIDE_APPLIED`.
* **Partitioning & Clustering**: Partitioned by `DAY` on `created_at`. Clustered by `[application_id, event_type]`.

### B. `financial_ledger_audit_log` (Core Accounting & Cards)
* **Regulatory Regime**: Sarbanes-Oxley (SOX), Anti-Money Laundering (AML), and PCI-DSS. Requires strict tamper-proof immutability for 5 to 7 years.
* **Core Events**: `MONETARY_TRANSFER_EXECUTED`, `CREDIT_LIMIT_INCREASED`, `FEE_REVERSED`, `CARD_FROZEN`.
* **Partitioning & Clustering**: Partitioned by `MONTH` on `created_at`. Clustered by `[account_id, event_type]`.

### C. `identity_access_audit_log` (IAM & Messaging)
* **Regulatory Regime**: GDPR / CCPA right-to-be-forgotten rules. Supports cryptographic shredding and pseudonymization.
* **Core Events**: `USER_CREATED`, `DEVICE_REGISTERED`, `MESSAGE_SENT`.
* **Partitioning & Clustering**: Partitioned by `DAY` on `created_at`. Clustered by `[user_id, event_type]`.

### D. `system_config_audit_log` (System Pricing & Catalog Policies)
* **Regulatory Regime**: Truth in Lending (TILA), Truth in Savings (TISA), SOX internal control guidelines. Requires preserving pricing rate updates and limits policies modification history.
* **Core Events**: `CREDIT_PRODUCT_CATALOG_UPDATED`, `DEPOSIT_PRODUCT_CATALOG_UPDATED`, `SYSTEM_FEATURE_FLAG_MODIFIED`.
* **Partitioning & Clustering**: Partitioned by `MONTH` on `created_at`. Clustered by `[product_code, event_type]`.

---

## ⚙️ 3. Transactional Outbox Pipeline & Ingestion Architecture

To guarantee zero loss of compliance audit events without introducing network latency or locks into real-time customer banking workflows, we implement the **Transactional Outbox Pattern** across a 3-phase lifecycle:

```mermaid
sequenceDiagram
    participant App as Banking Service (OLTP)
    participant PG as Cloud SQL (PostgreSQL)
    participant Endpoint as POST /internal/process-outbox
    participant PubSub as Pub/Sub (audit-events)
    participant BQ as BigQuery (compliance_audit)

    Note over App,PG: Phase 1: ACID Transaction Boundary
    App->>PG: BEGIN TRANSACTION
    App->>PG: Execute Domain Mutation (e.g. Application / Override)
    App->>PG: INSERT audit.audit_outbox (status = 'PENDING')
    App->>PG: COMMIT TRANSACTION

    Note over Endpoint,PubSub: Phase 2: Outbox Draining Worker
    Endpoint->>PG: SELECT * FROM audit.audit_outbox WHERE status = 'PENDING'
    Endpoint->>PubSub: Publish JSON Message structured for BigQuery Schema
    PubSub-->>Endpoint: ACK (Message ID)
    Endpoint->>PG: UPDATE audit.audit_outbox SET status = 'PUBLISHED'

    Note over PubSub,BQ: Phase 3: Serverless OLAP Streaming
    PubSub->>BQ: Direct Subscription streams JSON via Storage Write API
```

### A. Phase 1: ACID Transaction Boundary (`record_audit_event`)
When a state mutation occurs, the backend application writes the event into the PostgreSQL `audit.audit_outbox` table with `status = 'PENDING'` inside the exact same database transaction. This guarantees atomicity: if the transaction rolls back, the outbox record rolls back as well. No external network API calls are made during this synchronous phase.

### B. Phase 2: Outbox Draining Worker (`POST /internal/process-outbox`)
An asynchronous poller or scheduled trigger periodically invokes the draining endpoint. The worker queries pending records, formats each payload dictionary into top-level keys matching the regulatory schema (`event_id`, `event_type`, `created_at`, `payload`, `application_id`, `underwriter_id`), and dispatches them concurrently to the Google Cloud Pub/Sub topic `audit-events`. To prevent database connection pool starvation during network I/O, publish calls are dispatched non-blockingly in parallel; returned future objects are collected and resolved together prior to updating database rows to `status = 'PUBLISHED'`. Failed deliveries automatically retry and eventually transition to `DLQ` state after exceeding maximum retry attempts.

### C. Phase 3: Serverless OLAP Streaming (`audit-events-bq-sub`)
Google Cloud’s native **Pub/Sub BigQuery Subscription** ingests messages from `audit-events` directly into BigQuery (`compliance_audit.origination_audit_log`) via the high-throughput BigQuery Storage Write API. Configured with `--use-table-schema = true`, serverless GCP infrastructure maps JSON message attributes directly to BigQuery columns, consuming zero container CPU cycles.

---

## 🛡️ 4. Defense-in-Depth PII Protection & Guardrails

### A. Application-Layer Payload Filtering
Audit outbox logging utilities strictly serialize structural metadata, status deltas, and UUID references. Plaintext PII strings (such as plain SSNs, raw tax form strings, or unmasked account numbers) are stripped at the application layer prior to outbox serialization.

### B. Cryptographic Schema Isolation & KMS Envelope Encryption
Sensitive customer KYC records reside in an isolated PostgreSQL schema (`kyc.kyc_records`). PII is encrypted at rest using AES-256-GCM envelope encryption with Data Encryption Keys wrapped by Google Cloud KMS (`kyc-kek`). Encryption operations bind `user_id + kyc_record_id` as Additional Authenticated Data (AAD) to prevent ciphertext transplant attacks.

### C. BigQuery Data Catalog Policy Tags & Dynamic Masking
In OLAP tables, sensitive NPI columns enforce Google Cloud Data Catalog Policy Tags (`sensitive_npi`, `PII_HIGH`). Unauthorized analysts querying BigQuery automatically receive masked outputs (e.g. `XXX-XX-1234`) dynamically evaluated by GCP IAM without requiring custom database views.

### D. Mandatory Time Partitioning & Dedicated CMEK at Rest
Every analytical table enforces strict time partitioning (`require_partition_filter = true`) to prevent accidental full-table scans. Compliance audit streaming topics (`audit-events`) and BigQuery analytical datasets enforce Customer-Managed Encryption Keys at rest using a dedicated cryptographic key domain (`audit-cmek-key`), ensuring full blast radius containment separated from Document AI processing pipelines.
