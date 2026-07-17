# 🏛️ FSI Banking Platform Architecture Documentation

Welcome to the central engineering and systems architecture repository for the enterprise banking platform. Our documentation is organized into domain-specific subdirectories to facilitate rapid onboarding, system scannability, and architectural governance.

---

## 📊 1. Data Platform & Lakehouse (`data-platform/`)
Specifications covering our transactional database schemas, continuous deployment migration governance, real-time Change Data Capture (CDC), and multi-engine OLAP lakehouse analytics.

| Specification | Description |
| :--- | :--- |
| **[CDC and Apache Iceberg Lakehouse](./data-platform/apache_iceberg_cdc_datalake_architecture.md)** | Complementary native-BigQuery Datastream CDC and catalog-native Iceberg audit/financial-event paths, with cross-engine Spark access. |
| **[BigQuery OLAP & Compliance Audit Architecture](./data-platform/bigquery_olap_audit_architecture.md)** | Transactional outbox relay, Pub/Sub/Dataflow Managed Iceberg delivery, logical deduplication, and catalog interoperability. |
| **[Transactional Data Layer Architecture](./data-platform/data_layer_architecture.md)** | PostgreSQL Bounded Context domain schemas (`cards`, `origination`, `identity`, `ledger`), UUID generation, and advisory-locked deployment governance. |
| **[Data Generator Architecture](./data-platform/data_generator_architecture.md)** | Synthetic transaction generation, durable scheduler ownership, Cloud Tasks dispatch, and FastMCP controls. |
| **[Pre-Deployment Migrations & CI/CD Strategy](./data-platform/pre_deployment_migrations_plan.md)** | Ephemeral container validation, Alembic migration orchestration in Cloud Build, and zero-downtime schema rollout protocols. |
| **[Alembic Schema Migrations](./data-platform/alembic_schema_migrations.md)** | Multi-schema Alembic env, `admin` version table, `pg_advisory_xact_lock` concurrency guard, autogenerate governance, and SQLite test compatibility. |
| **[Secure Database Access via IAP SSH Tunnel](./data-platform/iap_ssh_tunnel_database_access.md)** | Private AlloyDB access through a bastion with `gcloud compute ssh --tunnel-through-iap`, port forwarding, and short-lived IAM access-token authentication. |
| **[Knowledge Catalog Fraud Support Guidance](./data-platform/knowledge_catalog_fraud_support_guidance.md)** | Dataplex Knowledge Catalog entry/aspect model, sync job, fallback behavior, and runtime guidance flow for fraud voice support. |
| **[Financial Ledger & Double-Entry Journal](./data-platform/financial_ledger_journal_architecture.md)** | Balanced double-entry posting primitive, idempotency and replay safety, system clearing accounts, and versioned `FINANCIAL_TRANSACTION_POSTED` events. |

---

## 🤖 2. AI, Multimodal & Voice Agents (`ai-and-voice/`)
Specifications detailing our Google Cloud AI integrations, conversational telephony interfaces, and document extraction pipelines.

| Specification | Description |
| :--- | :--- |
| **[Gemini Multimodal Live Voice Agent](./ai-and-voice/gemini_live_voice_agent.md)** | Bidirectional WebSocket voice streaming, PyTorch CPU optimization, and real-time tool orchestration with Gemini Live. |
| **[GECX Telephony Voice Agent](./ai-and-voice/gecx_telephony_voice_agent.md)** | Google Enterprise Contact Center Experience (GECX) integration, SIP telephony bridging, and conversational customer support workflows. |
| **[Document AI Processing Pipeline](./ai-and-voice/doc_ai_processing_pipeline.md)** | Asynchronous optical character recognition (OCR) and structured entity extraction for W-2 tax forms, paystubs, and bank statements. |
| **[Enterprise Search & Generative Answers](./ai-and-voice/enterprise_search_and_answers.md)** | Vertex AI Discovery Engine ranked search and grounded conversational answers over the bank's published content. |
| **[Knowledge Catalog Fraud Support Guidance](./data-platform/knowledge_catalog_fraud_support_guidance.md)** | Data-platform-owned Dataplex policy guidance consumed by the Gemini Live credit support agent at session startup. |

---

## 💼 3. Domain Workflows & Origination (`domain-workflows/`)
Specifications detailing customer-facing banking journeys, loan origination pipelines, and back-office customer support integrations.

### 📝 A. Origination & Onboarding (`domain-workflows/origination/`)
| Specification | Description |
| :--- | :--- |
| **[Credit Card Prefill Integration](./domain-workflows/origination/credit_card_prefill_integration.md)** | Automated credit card origination workflows, credit score verification, and instant card issuance pipelines. |
| **[Home Loan Preapproval Integration](./domain-workflows/origination/home_loan_preapproval_integration.md)** | Mortgage pre-approval funnels, automated income verification checklists, and underwriter exception routing. |

### 💳 B. Account Servicing & Self-Service (`domain-workflows/servicing/`)
| Specification | Description |
| :--- | :--- |
| **[Cardholder Self-Service & Account Servicing](./domain-workflows/servicing/cardholder_self_service.md)** | Bill payment, credit-line increases, fee dispute/reversal, and card freeze/replacement with effective-customer resolution and ledger-backed money movement. |
| **[Branch & ATM Locator](./domain-workflows/servicing/branch_atm_locator.md)** | Device-location, geocoded-address, and text-fallback nearest-location search from the UI and the GECX locator agent. |

### 🔗 C. Open Banking & Data Sharing (`domain-workflows/open-banking/`)
| Specification | Description |
| :--- | :--- |
| **[FDX v6 Open Banking Integration](./domain-workflows/open-banking/fdx_open_banking_integration.md)** | Scope-gated FDX v6 account, balance, transaction, and payment-network endpoints with MCC personal-finance categorization and first-party contract parity. |

### 💬 D. Customer Support & Messaging (`domain-workflows/support/`)
| Specification | Description |
| :--- | :--- |
| **[Secure Messaging Backend Integration](./domain-workflows/support/secure_messaging_backend_integration.md)** | Eventarc event-driven messaging, Firebase Cloud Messaging (FCM) mobile push notifications, and customer support threads. |
| **[Live Agent Escalation & Human Handoff](./domain-workflows/support/live_agent_escalation.md)** | AI-to-human escalation queue, LiveKit room takeover, agent identity binding, and escalation lifecycle. |

### 🛡️ E. Fraud Detection & Remediation (`domain-workflows/fraud/`)
| Specification | Description |
| :--- | :--- |
| **[Fraud Detection Workflow](./domain-workflows/fraud/fraud_detection_workflow.md)** | Real-time card authorization scoring, merchant/location enrichment, fraud alert creation, support triage, and CDC-backed analytical decision history. |
