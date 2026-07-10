# 🏛️ FSI Banking Platform Architecture Documentation

Welcome to the central engineering and systems architecture repository for the enterprise banking platform. Our documentation is organized into domain-specific subdirectories to facilitate rapid onboarding, system scannability, and architectural governance.

---

## 📊 1. Data Platform & Lakehouse (`data-platform/`)
Specifications covering our transactional database schemas, continuous deployment migration governance, real-time Change Data Capture (CDC), and multi-engine OLAP lakehouse analytics.

| Specification | Description |
| :--- | :--- |
| **[Apache Iceberg CDC Data Lakehouse](./data-platform/apache_iceberg_cdc_datalake_architecture.md)** | Real-time Datastream CDC replication into BigLake Iceberg Parquet manifests, Hidden Partitioning evolution, and Medallion Silver/Gold curated reporting views. |
| **[BigQuery OLAP & Compliance Audit Architecture](./data-platform/bigquery_olap_audit_architecture.md)** | SOX/GLBA-compliant immutable audit logging, Pub/Sub Storage Write API streaming, and KMS/Data Catalog PII column masking. |
| **[Transactional Data Layer Architecture](./data-platform/data_layer_architecture.md)** | PostgreSQL Bounded Context domain schemas (`cards`, `origination`, `identity`, `ledger`), UUID generation, and advisory-locked deployment governance. |
| **[Pre-Deployment Migrations & CI/CD Strategy](./data-platform/pre_deployment_migrations_plan.md)** | Ephemeral container validation, Alembic migration orchestration in Cloud Build, and zero-downtime schema rollout protocols. |
| **[Knowledge Catalog Fraud Support Guidance](./data-platform/knowledge_catalog_fraud_support_guidance.md)** | Dataplex Knowledge Catalog entry/aspect model, sync job, fallback behavior, and runtime guidance flow for fraud voice support. |

---

## 🤖 2. AI, Multimodal & Voice Agents (`ai-and-voice/`)
Specifications detailing our Google Cloud AI integrations, conversational telephony interfaces, and document extraction pipelines.

| Specification | Description |
| :--- | :--- |
| **[Gemini Multimodal Live Voice Agent](./ai-and-voice/gemini_live_voice_agent.md)** | Bidirectional WebSocket voice streaming, PyTorch CPU optimization, and real-time tool orchestration with Gemini Live. |
| **[GECX Telephony Voice Agent](./ai-and-voice/gecx_telephony_voice_agent.md)** | Google Enterprise Contact Center Experience (GECX) integration, SIP telephony bridging, and conversational customer support workflows. |
| **[Document AI Processing Pipeline](./ai-and-voice/doc_ai_processing_pipeline.md)** | Asynchronous optical character recognition (OCR) and structured entity extraction for W-2 tax forms, paystubs, and bank statements. |
| **[Knowledge Catalog Fraud Support Guidance](./data-platform/knowledge_catalog_fraud_support_guidance.md)** | Data-platform-owned Dataplex policy guidance consumed by the Gemini Live credit support agent at session startup. |

---

## 💼 3. Domain Workflows & Origination (`domain-workflows/`)
Specifications detailing customer-facing banking journeys, loan origination pipelines, and back-office customer support integrations.

### 📝 A. Origination & Onboarding (`domain-workflows/origination/`)
| Specification | Description |
| :--- | :--- |
| **[Credit Card Prefill Integration](./domain-workflows/origination/credit_card_prefill_integration.md)** | Automated credit card origination workflows, credit score verification, and instant card issuance pipelines. |
| **[Home Loan Preapproval Integration](./domain-workflows/origination/home_loan_preapproval_integration.md)** | Mortgage pre-approval funnels, automated income verification checklists, and underwriter exception routing. |

### 💬 B. Customer Support & Messaging (`domain-workflows/support/`)
| Specification | Description |
| :--- | :--- |
| **[Secure Messaging Backend Integration](./domain-workflows/support/secure_messaging_backend_integration.md)** | Eventarc event-driven messaging, Firebase Cloud Messaging (FCM) mobile push notifications, and customer support threads. |

### 🛡️ C. Fraud Detection & Remediation (`domain-workflows/fraud/`)
| Specification | Description |
| :--- | :--- |
| **[Fraud Detection Workflow](./domain-workflows/fraud/fraud_detection_workflow.md)** | Real-time card authorization scoring, merchant/location enrichment, fraud alert creation, support triage, and CDC-backed analytical decision history. |
