# Data Platform Architecture

This folder documents the platform layer that moves operational banking data from transactional systems into analytical, governed, and AI-consumable surfaces.

| Specification | Description |
| :--- | :--- |
| [Apache Iceberg CDC Data Lakehouse](./apache_iceberg_cdc_datalake_architecture.md) | Real-time Datastream CDC replication into BigLake Iceberg and curated analytics views. |
| [BigQuery OLAP & Compliance Audit Architecture](./bigquery_olap_audit_architecture.md) | Audit logging, compliance posture, BigQuery analytical patterns, and governed data access. |
| [Transactional Data Layer Architecture](./data_layer_architecture.md) | PostgreSQL bounded-context schemas, data ownership, and transactional model design. |
| [Data Generator Architecture](./data_generator_architecture.md) | Synthetic transaction generation, durable scheduler ownership, Cloud Tasks dispatch, and FastMCP controls. |
| [Pre-Deployment Migrations & CI/CD Strategy](./pre_deployment_migrations_plan.md) | Migration validation, deployment sequencing, and database rollout governance. |
| [Alembic Schema Migrations](./alembic_schema_migrations.md) | Multi-schema Alembic mechanics: `admin` version table, `pg_advisory_xact_lock` concurrency, autogenerate governance, and offline/online modes. |
| [Secure Database Access via IAP SSH Tunnel](./iap_ssh_tunnel_database_access.md) | Private AlloyDB access through a bastion using `gcloud compute ssh --tunnel-through-iap`, local port forwarding, and short-lived IAM token authentication. |
| [Lakehouse View Reconciliation](./lakehouse_view_reconciliation.md) | Curated view reconciliation, deployment safety, and BigQuery view lifecycle behavior. |
| [Real Time Analytics Agent Architecture](./real_time_analytics_agent_architecture.md) | Managed Gemini Data Analytics agent grounding, deployment lifecycle, IAM boundaries, and runtime query flow. |
| [Knowledge Catalog Fraud Support Guidance](./knowledge_catalog_fraud_support_guidance.md) | Dataplex Knowledge Catalog guidance artifacts consumed by fraud support workflows. |
| [Financial Ledger & Double-Entry Journal](./financial_ledger_journal_architecture.md) | Balanced double-entry posting primitive, idempotency, system clearing accounts, and versioned financial events. |

Workflow-specific behavior belongs in [Domain Workflows](../domain-workflows/README.md). Voice, agent, and multimodal integration details belong in [AI & Voice](../ai-and-voice/).
