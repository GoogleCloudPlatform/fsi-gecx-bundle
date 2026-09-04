# Gemini Enterprise BigQuery A2A Operations

## Scope

This runbook provisions and validates the environment-local Gemini Enterprise application and its
A2A connection to the `real-time-analytics` Gemini Data Analytics agent. It covers
`evo-genai-workspace` and the prod-like `fsi-demo-1841` environment.

The integration is deliberately hybrid:

| Operation | Automation boundary |
| :--- | :--- |
| APIs, IAM, Gemini Enterprise app, app features, and deletion protection | Terraform |
| BigQuery DataAgent creation, update, source validation, and drift detection | Repository deployment script or Cloud Build trigger |
| A2A authorization and agent registration | Supported Discovery Engine REST API or console |
| Standard Google OAuth web-client creation | Manual Google Auth Platform action; Google prohibits programmatic creation |
| Identity-provider selection, subscription purchase, and initial administrative setup | Manual project or billing-account administration |
| End-user consent | Manual per-user OAuth consent |

## Environment Configuration

| Project | App ID | Display name | Region |
| :--- | :--- | :--- | :--- |
| `evo-genai-workspace` | `nova-horizon-dev-workbench` | Nova Horizon Dev Workbench | `us` |
| `fsi-demo-1841` | `nova-horizon-banking-demo` | Nova Horizon Banking Demo | `us` |

The stable DataAgent ID is `real-time-analytics` in both projects. Its A2A endpoint embeds the
target project and must not be copied from another environment.

## Prerequisites

Before provisioning an app, confirm:

- Gemini Enterprise Standard or a higher compatible subscription is active for the target billing
  account and `us` multi-region.
- Discovery Engine, Gemini Data Analytics, BigQuery, IAM, and Service Usage APIs are enabled.
- The operator has Gemini Enterprise Admin, DataAgent deployment, and required project IAM.
- The deployment principal can read metadata and data from every configured BigQuery source.
- The end user has Gemini Enterprise User, DataAgent user/viewer, BigQuery Job User, and dataset
  access appropriate to the requested analysis.

## 1. Provision or Import the Gemini Enterprise App

The optional `gemini_enterprise_app` environment value enables the Terraform resource. Initialize
Terraform with the target environment's backend and review a normal plan before applying.

```shell
terraform -chdir=deployment/terraform init -reconfigure -input=false \
  -backend-config=environment/PROJECT_ID/gcs.tfbackend

terraform -chdir=deployment/terraform plan -input=false \
  -var-file=environment/PROJECT_ID/terraform.tfvars
```

Import a pre-existing app before the first apply:

```shell
terraform -chdir=deployment/terraform import -input=false \
  -var-file=environment/PROJECT_ID/terraform.tfvars \
  'google_discovery_engine_search_engine.gemini_enterprise["app"]' \
  'projects/PROJECT_ID/locations/us/collections/default_collection/engines/APP_ID'
```

Terraform sets the app type, subscription tier, LLM add-on, sharing features, and deletion policy.
It outputs the administrative dashboard URL. The end-user URL contains a generated configuration
ID and must be copied from the dashboard after the app is ready.

## 2. Reconcile the BigQuery DataAgent

Reconcile curated views before deploying the agent. Then deploy the same project-neutral agent
specification into the target project:

```shell
python3 deployment/data_agents/deploy_data_agent.py \
  --project=PROJECT_ID \
  --spec=deployment/data_agents/real_time_analytics_agent.json
```

Verify that the deployed resource matches source control:

```shell
python3 deployment/data_agents/deploy_data_agent.py \
  --project=PROJECT_ID \
  --spec=deployment/data_agents/real_time_analytics_agent.json \
  --check
```

Do not continue if source validation or the drift check fails.

## 3. Create the Environment OAuth Client

Google requires this step in Google Auth Platform and does not permit ordinary OAuth clients to be
created or modified programmatically.

Create a **Web application** client in the same project as the target BigQuery data. Use a distinct
name such as `Nova Horizon Gemini Enterprise A2A` and configure exactly these redirect URIs:

```text
https://vertexaisearch.cloud.google.com/oauth-redirect
https://vertexaisearch.cloud.google.com/static/oauth/oauth.html
```

Capture the one-time client ID and secret in an approved credential store. Do not put either value
in `terraform.tfvars`, source control, shell history, tickets, screenshots retained in shared photo
libraries, or documentation.

## 4. Generate and Register the Target A2A Card

In BigQuery, open `real-time-analytics`, publish it to Gemini Enterprise, and copy the generated
A2A card JSON. Verify before registration that:

- `description` matches the source-controlled routing description.
- `url` contains the target project and `locations/us/dataAgents/real-time-analytics`.
- Every dataset/table reference belongs to the target project.
- The card contains no OAuth secret.

In the target Gemini Enterprise app, add **Custom agent via A2A** and paste the card. Configure the
authorization with:

```text
Authorization endpoint: https://accounts.google.com/o/oauth2/v2/auth
Token endpoint:         https://oauth2.googleapis.com/token
Scope:                  https://www.googleapis.com/auth/cloud-platform
```

The authorization URL must include the OAuth client ID, the static Gemini Enterprise redirect URI,
`include_granted_scopes=true`, `response_type=code`, `access_type=offline`, and `prompt=consent`.
Store the resulting authorization and agent registration only in the target project.

The Discovery Engine REST API supports idempotent registration automation even though the current
Terraform provider does not expose the registered A2A agent as a first-class resource. Any REST
reconciler must read the OAuth secret from an approved secret store and must never render it in a
plan, log, or committed payload.

## 5. Configure Identity, IAM, and Licenses

Use Google Identity for these environments. In **Manage users**, select the `us` multi-region and
confirm:

- The Standard subscription is active.
- A seat is assigned to each demo user or automatic assignment targets the intended subscription.
- Automatically updating expired licenses matches the demo operating policy.

Selecting `global` while the app and subscription are in `us` can misleadingly show no licenses.

### Shared presenters in FSI Demo 1841

Add authorized Google presenters to:

```text
fsi-nova-horizon-demo-console-viewer@google.com
```

The `iam_console_viewers` configuration already grants this group the bounded BigQuery and
DataAgent roles required by the analytics agent. When `gemini_enterprise_app` is enabled,
Terraform also grants the same principals `roles/discoveryengine.agentspaceUser`. Automatic
license assignment then allocates an individual 1841 `us` seat when a group member first signs in.
Each presenter must complete the A2A OAuth consent flow on first invocation.

Removing a presenter from the group revokes IAM-backed application and data access, but it does
not reclaim the separately assigned Gemini Enterprise license. Reclaim unused seats through
**Manage users** when appropriate.

Do not add the shared presenter group to `evo-genai-workspace`; Evo is the owner's personal
development sandbox. A user who genuinely needs both projects requires separate project/location
license assignments.

## 6. Obtain the End-User URL

Terraform reads the app's `default_search_widget_config`, obtains its generated `configId`, and
composes the environment-local end-user URL. Retrieve it after apply with:

```bash
terraform output -raw gemini_enterprise_web_url
```

A `us` URL has this shape:

```text
https://vertexaisearch.cloud.google.com/us/home/cid/GENERATED_CONFIGURATION_ID
```

Do not substitute the project number or engine ID for `GENERATED_CONFIGURATION_ID`. The generated
widget `configId` is different in every environment; substituting another identifier can resolve
against the wrong location or return a false "not assigned an active license" error.

## 7. Verify End to End

Open the end-user URL, select **Real Time Analytics Agent**, complete first-use OAuth consent, and
run a low-risk aggregate prompt:

```text
Provide a breakdown of our US customer base by major metropolitan area, ranked from highest to
lowest customer count, with the percentage of total customers each area represents.
```

Verify:

- The agent is displayed as enabled with the current routing description.
- OAuth consent references the expected client and scope.
- The answer is returned through the target environment's agent.
- The response identifies the source view and relevant time/filter semantics.
- No raw customer identifiers or audit payloads are exposed.

Then rehearse the VIP Mexico-spend chart prompt documented in
`deployment/data_agents/README.md`.

## Update and Drift Procedure

When the JSON specification changes:

1. Deploy and `--check` the DataAgent in each environment.
2. Regenerate each environment's A2A card.
3. Patch the outer Gemini Enterprise description and the embedded card together.
4. Preserve the existing environment-local authorization reference.
5. Repeat the end-to-end aggregate prompt.

An update to the source DataAgent does not automatically refresh an existing Gemini Enterprise A2A
registration.

## Troubleshooting

| Symptom | Check |
| :--- | :--- |
| App opens with a license 400 | Copy the dashboard-generated URL and confirm both app and license view use `us`. |
| Agent is visible but invocation requests authorization | Complete first-use consent and verify the environment-local OAuth client and redirect URIs. |
| Agent description is old | Reconcile the DataAgent, regenerate the card, and patch both registered description fields. |
| Query reports missing sources | Run the source validator; confirm `oltp_cdc`, `analytics_curated`, and `compliance_audit` objects exist in the target. |
| User can open the agent but BigQuery fails | Check user-level BigQuery Job User and dataset permissions; agent sharing does not grant data access. |
| New 1841 presenter cannot open the app | Confirm group membership has propagated, Terraform applied the Gemini Enterprise User role, and an individual `us` license is available or assigned. |
| Terraform wants to recreate a manual app | Import the existing engine into the target environment's state before apply. |

For the design rationale and security boundary, see
[Gemini Enterprise BigQuery A2A Architecture](../architecture/ai-and-voice/gemini_enterprise_bigquery_a2a.md).
