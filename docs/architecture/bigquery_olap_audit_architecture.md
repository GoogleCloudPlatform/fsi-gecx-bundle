# 🏛️ BigQuery OLAP Audit & Compliance Architecture Blueprint

This document specifies the Enterprise OLAP Data Warehousing and Compliance Auditing architecture for the Nova Horizon Banking Platform. It defines our domain-segmented BigQuery auditing strategy, mandatory partitioning guardrails, and FSI regulatory compliance rules.

---

## 🌐 1. Executive Summary & OLAP Topology

To achieve FSI regulatory compliance across equal credit opportunity, anti-money laundering, and data privacy laws, our platform separates live transactional OLTP processing (Cloud SQL PostgreSQL) from immutable analytical warehousing (Google Cloud BigQuery).

Rather than dumping disparate system events into a single monolithic audit table, we establish a dedicated **`compliance_audit`** dataset in BigQuery segmented by Bounded Context workflows:

```mermaid
graph TD
    subgraph OLTP - Cloud SQL PostgreSQL
        Outbox[audit.audit_outbox]
    end

    subgraph OLAP - BigQuery compliance_audit Dataset
        ORIG[origination_audit_log<br/>Partitioned: DAY | Clustered: application_id, event_type<br/>Retention: 10 Years ECOA]
        FIN[financial_ledger_audit_log<br/>Partitioned: MONTH | Clustered: account_id, event_type<br/>Retention: 7 Years SOX/AML Immutable]
        ID[identity_access_audit_log<br/>Partitioned: DAY | Clustered: user_id, event_type<br/>Retention: 3 Years GDPR/CCPA]
    end

    Outbox -->|PubSub / Storage Write API| ORIG & FIN & ID
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

---

## ⚙️ 3. Staff DBA Best Practices & Guardrails

### A. Mandatory Time Partitioning & `require_partition_filter`
Every analytical table enforce strict time partitioning. To prevent automated BI tools or ad-hoc queries from executing accidental multi-year full-table scans that consume massive GCP query budgets, all audit tables configure `require_partition_filter = true`.

### B. High-Throughput Ingestion via BigQuery Storage Write API
To eliminate DML quota bottlenecks and query planning overhead, outbox event streaming utilizes the **BigQuery Storage Write API (gRPC)** or direct Pub/Sub subscriptions for sub-second, exact-once ingestion.

### C. Native `JSON` Search Indexes
Unstructured OCR payloads (`extraction_payload`) and audit traces (`audit_metadata`) utilize native BigQuery `JSON` column typing paired with search indexes (`CREATE SEARCH INDEX`). This allows instant text search across nested W-2 and paystub fields during fraud investigations.

### D. Universal CMEK & Policy Tags
All audit tables enforce Customer-Managed Encryption Keys (CMEK) and Google Cloud Data Catalog Policy Tags (`PII_HIGH`, `PII_STANDARD`), guaranteeing automatic column masking for unauthorized readers.
