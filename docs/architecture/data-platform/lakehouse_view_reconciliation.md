# Lakehouse Curated View Reconciliation

## Purpose

The `analytics_curated` dataset contains Silver/Gold BigQuery views over bronze Datastream tables in `iceberg_catalog`. Those bronze tables are created asynchronously by Datastream, so curated views must not be a deployment gate.

This environment uses an explicit, idempotent reconciliation job instead:

- Terraform owns durable infrastructure: Datastream, datasets, IAM, the Cloud Run Job, and the daily scheduler.
- SQL files remain the source of truth for curated views.
- A manifest declares each view's source tables.
- The reconciliation container is built by the data-platform Cloud Build config, not by the banking-service image pipeline.
- Deployment starts reconciliation once without waiting for it.
- Cloud Scheduler runs reconciliation daily as a low-noise drift repair pass.
- Operators can run the Cloud Run Job manually whenever a repair is needed.

## Runtime Flow

1. Terraform creates Datastream in `NOT_STARTED` state and provisions `iceberg_catalog` plus `analytics_curated`.
2. The database migration job creates PostgreSQL CDC prerequisites: replication grants, publication, and logical replication slot.
3. The ordered release drains and pauses Datastream before a full reset because PostgreSQL `TRUNCATE` is not replicated.
4. After reset, the release recreates stream-owned BigQuery tables with the configured freshness target, resumes Datastream, and requires every configured object backfill to complete.
5. The release then runs `lakehouse-view-reconcile` synchronously. It does not build the reconcile image.
6. The reconcile job verifies the Datastream stream, checks each view's declared source tables, and applies only views whose dependencies are queryable.
7. A daily Cloud Scheduler job runs the same reconcile job to repair missed first-pass setup or later drift.

The reconciliation image is built from:

```text
deployment/lakehouse-reconcile/cloudbuild.yaml
```

That Cloud Build trigger watches:

- `deployment/lakehouse-reconcile/**`
- `deployment/bigquery/analytics_curated/**`
- `scripts/datastream/reconcile_lakehouse_views.py`

The reconcile job exits successfully when source tables are not ready yet and no hard errors occurred. Missing bronze tables are expected during fresh environment bring-up.

## Adding a Curated View

Add the SQL file under:

```text
deployment/bigquery/analytics_curated/view/
```

Use the project placeholder in fully qualified table names:

```sql
CREATE OR REPLACE VIEW `__PROJECT_ID__.analytics_curated.example_view` AS
SELECT ...
FROM `__PROJECT_ID__.iceberg_catalog.cards_transaction_authorization`;
```

Then add an entry to:

```text
deployment/bigquery/analytics_curated/views.json
```

Example:

```json
{
  "name": "example_view",
  "sql": "example_view.sql",
  "sources": [
    "iceberg_catalog.cards_transaction_authorization"
  ]
}
```

Each source must be formatted as `dataset.table`. The reconcile job validates readiness by running a trivial BigQuery query against each source before applying the view.

## Operating the Job

Run reconciliation manually:

```bash
gcloud run jobs execute lakehouse-view-reconcile \
  --region "${REGION:-us-central1}" \
  --wait
```

Inspect recent executions:

```bash
gcloud run jobs executions list \
  --job lakehouse-view-reconcile \
  --region "${REGION:-us-central1}"
```

View logs:

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="lakehouse-view-reconcile"' \
  --limit 50 \
  --format json
```

## Scheduling Policy

The demo environment intentionally avoids noisy frequent polling:

- The ordered release waits for one immediate reconcile pass after CDC backfill.
- Cloud Scheduler runs one daily reconcile pass.
- Manual execution remains available for demos, repairs, and new view testing.

If a future demo needs an exact "five minutes after deploy" retry, add Cloud Tasks and enqueue a delayed Cloud Run Job invocation from Cloud Build. Cloud Scheduler is cron-based, so Cloud Tasks is the cleaner primitive for deploy-relative delays.
