# AlloyDB Demo Operations Runbook

For the routine build, qualification, and promotion procedure, start with
[Build and deploy](build_and_deploy.md). This runbook covers AlloyDB-specific
operations, recovery, CDC diagnosis, and the historical one-time Cloud SQL
cutover.

## Environment roles

- Evo and each contributor-owned project are developer environments. Any configured developer environment can qualify a release candidate.
- `fsi-demo-1841` is the prod-like, field-facing showcase environment. Deploy it only from an approved qualified manifest.
- Developer environments use a zonal 2-vCPU primary. `fsi-demo-1841` uses a regional HA primary.

## Ordered deployment

### Release IAM prerequisites

Each environment that uploads source archives with `gcloud builds submit` must set `cloudbuild_source_bucket_name` to its existing `PROJECT_ID_cloudbuild` bucket. Terraform grants that environment's custom `cloudbuild-sa` `roles/storage.objectViewer` on only that bucket so the build worker can read the archive uploaded by the caller.

Each developer environment that can qualify a release must grant, at minimum, the following promotion-target principals access to its Artifact Registry repository through `release_image_consumer_members`:

- The target `cloudbuild-terraform-sa`, which verifies and deploys the qualified digests.
- The target Cloud Run service agent (`service-PROJECT_NUMBER@serverless-robot-prod.iam.gserviceaccount.com`), which imports cross-project images for Cloud Run services and jobs.

Additional runtime or lifecycle principals may remain in the list when release tooling needs them, but they do not replace either required promotion principal.

The promotion target's `cloudbuild-terraform-sa` must also appear in `release_manifest_reader_members`. These grants belong to the qualifying source project because it owns the release manifest bucket and immutable image repository. Do not repair a failed promotion with ad hoc project-wide roles; update the source environment's Terraform membership lists and apply them there.

Use `release-qualify` in the selected developer project. Supply the full Git commit in `_RELEASE_COMMIT`. On the one-time destructive cutover, also override `_ALLOW_CLOUD_SQL_CUTOVER=true`; this records and retains a final Cloud SQL backup before deleting the legacy instance.

The trigger applies Terraform and then runs:

1. `banking-db-bootstrap`
2. `banking-db-migrate`
3. `banking-db-reconcile`
4. catalog-native Iceberg namespace/table and BigQuery-view bootstrap
5. Dataflow audit/financial-ledger pipeline build and launch/update
6. immutable-digest service rollout
7. Datastream drain/pause and `banking-db-reset`
8. Knowledge Catalog and BigQuery federation reconciliation
9. BigQuery CDC destination recreation and complete Datastream backfill
10. curated-view reconciliation
11. service, analytics, relay, and Iceberg smoke tests

A successful qualification writes `gs://PROJECT_ID-fsi-release-manifests/alloydb/COMMIT/qualify.json`.

To promote, run `release-promote` in `fsi-demo-1841` from the same commit, provide the qualification manifest URI, and approve the build. Promotion verifies and deploys the recorded image digests; it does not rebuild images or use `latest`.

## Connection diagnosis

1. Confirm the primary is ready: `gcloud alloydb instances describe banking-primary --cluster banking-data --region us-central1`.
2. Confirm the calling principal has `roles/alloydb.databaseUser` and `roles/serviceusage.serviceUsageConsumer`.
3. Confirm the matching AlloyDB IAM database user exists. Service-account usernames omit `.gserviceaccount.com`.
4. Confirm the workload has Direct VPC egress to `fsi-gecx-vpc` and that `DATABASE_URL` targets the primary private IP with `sslmode=require`.
5. Check Cloud Run logs for token refresh, TLS, pool timeout, or PostgreSQL privilege errors.
6. For an operator session, run `scripts/ssh-tunnel/connect-db.sh` and use a fresh `gcloud auth print-access-token` as the password.

IAM tokens are short lived. SQLAlchemy pools recycle connections before token expiry and use pre-ping; repeated authentication failures normally indicate IAM/user mismatch rather than a stale pooled token.

## Reset and seed

Run `scripts/reinit_postgres_db/reset_db_and_migrate.sh` for an ordered reset. It drains and pauses Datastream, verifies the database lifecycle, runs the guarded reset/seed job, reconciles federation, recreates stream-owned BigQuery destinations, resumes CDC, backfills every configured stream object, and then reconciles curated views. Do not drop schemas manually in a deployed environment.

This rebuild is required because Datastream does not replicate PostgreSQL `TRUNCATE`. Merely resuming the stream after a full demo reset leaves pre-reset rows in BigQuery. Recreating the tables also applies the stream's explicit 60-second BigQuery freshness setting; Datastream configuration changes do not retrofit that setting onto existing tables. The helper fails closed if the stream cannot pause or run, an object backfill fails, or all backfills do not complete within the bounded wait.

## CDC and federation health

- Datastream stream: `gcloud datastream streams describe banking-alloydb-oltp-cdc-stream --location us-central1`.
- Publication: `SELECT * FROM pg_publication WHERE pubname = 'datastream_publication';`
- Slot: `SELECT slot_name, active, restart_lsn, confirmed_flush_lsn FROM pg_replication_slots WHERE slot_name = 'datastream_alloydb_replication_slot';`
- Bridge: verify the `datastream-alloydb-proxy` systemd unit runs the digest-pinned `gcr.io/dms-images/tcp-proxy` image in host-network mode, inspect serial output, and verify TCP 5432 is allowed only from `172.16.1.0/29`.
- Federation: run `deployment/scripts/reconcile_alloydb_federation.sh`; it verifies `EXTERNAL_QUERY(..., 'SELECT 1')`.
- Audit relay: execute `audit-outbox-relay` once and verify its checkpoint advances with no old-message alert.
- Dataflow: verify `nova-audit-iceberg` is running, the Pub/Sub backlog is draining, and the Iceberg DLQ is empty.
- Catalog interoperability: run `deployment/scripts/validate_lakehouse_interoperability.sh`; it reads catalog-native Iceberg and native BigQuery CDC tables in one Spark session.

If the slot is inactive, check the bridge and Datastream source profile before recreating it. Never drop an active slot merely to clear lag; a backfill decision must be explicit.

## Restart, failover, and recovery

Cloud Run clients reconnect through the AlloyDB primary address. A regional primary can fail over between nodes without changing the application URL. During maintenance or failover, expect transient connection errors; pool pre-ping and request retry boundaries should recover after the primary becomes available.

For data recovery, use AlloyDB continuous backup/point-in-time recovery or a retained automated backup. Restore into a new cluster first, verify the Alembic revision and row-level invariants, then perform an explicit endpoint cutover. Do not overwrite the active showcase cluster during diagnosis.

The final pre-migration Cloud SQL backup identifier is stored in the first successful cutover manifest and retained for 30 days. Its purpose is emergency rollback during the migration window, not ongoing dual-engine operation.

## Demo preflight

- Banking, voice, and data-generator revisions reference immutable digests from the current manifest.
- `banking-db-reconcile` succeeds with expected Alembic revision `7c4f2a9d1e63`.
- Banking `/health`, authenticated voice `/`, and data-generator `/health` return success.
- A presenter reset/seed completes.
- Datastream is running, every configured backfill completed, and recent rows appear in BigQuery without pre-reset residue.
- BigQuery AlloyDB federation returns `SELECT 1`.
- The audit relay cursor advances, `nova-audit-iceberg` is running, and the catalog-native audit and ledger views return balanced, deduplicated rows.
- Knowledge Catalog sync and the Real Time Analytics agent source check succeed.
- Run one voice-support card workflow, one push notification, and the VIP Mexico-spend analytics question.
