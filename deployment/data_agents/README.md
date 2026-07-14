# Real Time Analytics Agent

The Real Time Analytics Agent is a Gemini Data Analytics `DataAgent` grounded in the banking
demo's environment-local BigQuery CDC catalog, curated analytical views, and compliance audit
views. The checked-in specification never contains a Google Cloud project ID. The deployment
script injects the target project into every explicit table reference.

The Google Terraform provider does not currently expose a native Gemini Data Analytics
`DataAgent` resource. Terraform therefore owns the required APIs, IAM, BigQuery prerequisites,
and a manual Cloud Build deployment trigger. The script owns idempotent DataAgent creation and
updates through the GA REST API.

## Deploy

After applying Terraform, run the `real-time-analytics-agent-deploy` Cloud Build trigger against
the branch or commit to deploy. The deployer validates every configured table or view before it
creates or updates the stable `real-time-analytics` agent in the `us` multi-region.

To render the payload locally without making API calls:

```shell
python3 deployment/data_agents/deploy_data_agent.py \
  --project=fsi-demo-1841 \
  --spec=deployment/data_agents/real_time_analytics_agent.json \
  --render
```

To check a deployed agent for configuration drift without changing it:

```shell
python3 deployment/data_agents/deploy_data_agent.py \
  --project=fsi-demo-1841 \
  --spec=deployment/data_agents/real_time_analytics_agent.json \
  --check
```

BigQuery DataAgents require explicit table references. Dataset-level IAM can grant users read
access, but it does not make a whole dataset an agent knowledge source. Keep the source allowlist
intentional: large source lists reduce accuracy and consume model context.

The DataAgent API validates knowledge sources with the deploying principal's credentials, so the
Cloud Build service account needs metadata and data-viewer access to all three source datasets.
The agent later queries BigQuery with the signed-in user's credentials. Users therefore also need
both the DataAgent/Cloud AI Companion roles and access to the underlying datasets.

## Demo questions

The curated layer intentionally supplies reusable, normalized data rather than pre-aggregated
answers. `customer_analytics_profiles` provides one row per customer with normalized geography,
credit profile, and account summary fields. `enriched_posted_transactions` remains at transaction
grain and includes customer, merchant geography, and positive `spend_amount_dollars` fields. The
agent joins, groups, ranks, and visualizes these views at request time.

The deployed agent is instructed and grounded to handle these exact demo questions:

1. **Create a horizontal bar chart showing the top 10 customers located in Northern California,
   ranked by their total spend in Mexico over the last 14 days. Sort the chart in descending order
   of total spend.**
2. **Provide a breakdown of our US customer base by major metropolitan area, ranked from highest
   to lowest customer count, along with the percentage of total customers each area represents.**

Deploy or reconcile the `analytics_curated` views before running the DataAgent deployment trigger;
the deployer deliberately rejects a source allowlist that references a missing view.
