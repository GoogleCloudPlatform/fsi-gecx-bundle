# Build and deploy

Nova Horizon has two intentionally different deployment paths:

| Path | Use it for | Destination | Safety boundary |
| --- | --- | --- | --- |
| Developer update | Fast iteration on one application component | The developer's own project | Builds and deploys directly; no qualification manifest |
| Qualified release | A release candidate and promotion to the field-facing environment | Any qualifying developer project, then `fsi-demo-1841` | Immutable image digests, ordered reconciliation, validation, manifest, and promotion approval |

`evo-genai-workspace` is a developer environment, not a universal staging
environment. A contributor may qualify from Evo or another correctly configured
developer project. `fsi-demo-1841` is the prod-like, field-facing environment and
must receive backend releases through promotion.

## Developer update

Use this path while developing and testing one component. It deliberately does
not create a release manifest and must not be used to deploy `fsi-demo-1841`.

```bash
gcloud config set project YOUR_DEVELOPER_PROJECT
make update COMPONENT=banking-ui BRANCH=feature/example
```

Supported components are `banking-service`, `banking-ui`,
`credit-support-agent`, and `data-generator`. The command runs that project's
existing component trigger with `_TRIGGER_DEPLOY=true`, streams the build, and
updates only that component. It refuses to run when `PROJECT_ID=fsi-demo-1841`.

For infrastructure changes, use a reviewed Terraform plan rather than
`make update`:

```bash
make tf-init ARGS="-reconfigure"
make tf-plan
make deploy
```

These developer operations mutate only the selected project. They do not prove
that the commit is promotable and they do not authorize copying a live revision
to the field-facing environment.

## Qualified release

The formal cycle is **build candidate → qualify → manually validate → promote**.
Use the same full commit SHA at every stage.

### 1. Build the release candidate

From the candidate branch, build the component images in the selected qualifying
developer project without deploying them:

```bash
export SOURCE_PROJECT=evo-genai-workspace
export BRANCH=feature/example
export COMMIT=$(git rev-parse origin/$BRANCH)
export ROLLBACK_MANIFEST="gs://$SOURCE_PROJECT-fsi-release-manifests/alloydb/LAST_KNOWN_GOOD_COMMIT/qualify.json"

gcloud config set project "$SOURCE_PROJECT"
make run-triggers BRANCH="$BRANCH"
```

Confirm that the `banking-service`, `banking-ui`, `credit-support-agent`, and
`data-generator` repositories each contain an image tagged with the full
`$COMMIT`. Qualification records their immutable digests; it never promotes
`latest`.

### 2. Qualify in the source environment

Run the manual `release-qualify` trigger at the exact commit:

```bash
gcloud builds triggers run release-qualify \
  --project="$SOURCE_PROJECT" \
  --region=us-central1 \
  --sha="$COMMIT" \
  --substitutions="_RELEASE_COMMIT=$COMMIT,_ROLLBACK_MANIFEST_URI=$ROLLBACK_MANIFEST"
```

Qualification applies Terraform, reconciles database grants and schema,
deploys the recorded service digests, resets and seeds the demo, synchronizes
the Knowledge Catalog, deploys the checked-out CES bundle to the configured
voice channel, rebuilds CDC destinations, reconciles federation and curated
analytics, updates the Iceberg pipeline, and runs automated health checks.
Success writes:

```text
gs://SOURCE_PROJECT-fsi-release-manifests/alloydb/COMMIT/qualify.json
```

The `alloydb` object prefix is retained for compatibility with existing
manifests; it does not mean the release is limited to AlloyDB.

### 3. Validate the candidate

Perform the short manual demo preflight in the source environment: sandbox
provisioning, voice/card support, push notification, VIP Mexico analytics, and
fresh CDC/analytics visibility. A successful build without these checks is not
an approved demo release.

### 4. Promote to `fsi-demo-1841`

Run the approval-gated `release-promote` trigger from the same commit and pass
the qualification manifest:

```bash
export TARGET_PROJECT=fsi-demo-1841
export MANIFEST="gs://$SOURCE_PROJECT-fsi-release-manifests/alloydb/$COMMIT/qualify.json"
export ROLLBACK_MANIFEST="gs://$TARGET_PROJECT-fsi-release-manifests/alloydb/LAST_KNOWN_GOOD_COMMIT/promote.json"

gcloud builds triggers run release-promote \
  --project="$TARGET_PROJECT" \
  --region=us-central1 \
  --sha="$COMMIT" \
  --substitutions="_RELEASE_COMMIT=$COMMIT,_MANIFEST_URI=$MANIFEST,_ROLLBACK_MANIFEST_URI=$ROLLBACK_MANIFEST"
```

Approve the pending build in Cloud Build. Promotion reads the source manifest,
verifies the commit, image digests, CES source digest and model, catalog
snapshot, and Alembic head, then runs the same ordered deployment and validation
controller in the target. It does not rebuild the container images.

## What the release manifest covers

The manifest pins and promotes these runtime images:

- `banking-service`
- `banking-ui`
- `credit-support-agent`
- `data-generator`

It also records and verifies:

- the content-addressed CES source bundle and native-live model
- the environment-local CES app, immutable version, and configured deployment
- the Knowledge Catalog seed snapshot
- the Alembic schema head
- one environment-local, previously successful manifest as the coherent
  rollback target

The release controller rejects a rollback manifest from another environment,
a manifest without successful validation, a mutable component image, or a
manifest that does not pin exactly one schema head. It records the rollback
manifest URI and digest together with its complete image, CES, catalog, and
database identity. Rollback selection is therefore one release unit rather
than an independently chosen set of component revisions. Database migrations
remain forward-only; the selected application rollback must be compatible with
the current schema head.

CES versions are project-local, so promotion imports the exact source-addressed
bundle and creates a target-local version rather than attempting to reuse the
source project's CES resource name. The configured deployment is the only CES
channel moved by the release controller.

IAP login UI and site crawling remain independent component triggers.

For AlloyDB recovery, CDC troubleshooting, reset behavior, and the one-time
Cloud SQL cutover procedure, see [AlloyDB demo operations](alloydb_demo_runbook.md).

Gemini Enterprise app provisioning, BigQuery DataAgent publication, environment-local OAuth/A2A
registration, licensing, and end-to-end checks are documented separately in
[Gemini Enterprise BigQuery A2A operations](gemini_enterprise_bigquery_a2a.md).
