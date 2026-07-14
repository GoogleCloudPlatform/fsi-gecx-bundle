# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

locals {
  trigger_by_branch = var.cloud_build_trigger_event == "push_to_branch"
  trigger_by_tag    = var.cloud_build_trigger_event == "push_to_tag"
}

resource "google_cloudbuild_worker_pool" "pool" {
  name     = "build-pool"
  location = var.region
  worker_config {
    disk_size_gb   = 100
    machine_type   = "n2d-standard-4"
    no_external_ip = false
  }
  network_config {
    peered_network          = google_compute_network.fsi_gecx_vpc.id
    peered_network_ip_range = "/29"
  }
  depends_on = [google_service_networking_connection.private_vpc_connection]
}

resource "google_cloudbuildv2_connection" "github_connection" {
  count    = var.deploy_cloud_build_triggers && var.manage_github_connection ? 1 : 0
  location = var.region
  name     = var.github_connection_name

  github_config {
    app_installation_id = var.github_app_installation_id
    authorizer_credential {
      oauth_token_secret_version = data.google_secret_manager_secret_version_access.github_token_secret_version[0].name
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.github_token_secret_accessor
  ]
}

resource "google_cloudbuildv2_repository" "fsi_gecx_bundle" {
  count             = var.deploy_cloud_build_triggers ? 1 : 0
  name              = "fsi-gecx-bundle"
  location          = var.region
  parent_connection = var.github_connection_name # google_cloudbuildv2_connection.github_connection[0].name
  remote_uri        = var.github_repo_remote_uri

  depends_on = [google_cloudbuildv2_connection.github_connection]
}

resource "google_cloudbuild_trigger" "service_deploy_trigger" {
  count    = var.deploy_cloud_build_triggers ? 1 : 0
  name     = "banking-service-deployment"
  location = var.region
  tags     = ["banking-service", "deploy"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
    push {
      branch = local.trigger_by_branch ? var.repo_branch_expression : null
      tag    = local.trigger_by_tag ? var.repo_tag_expression : null
    }
  }

  service_account = google_service_account.cloudbuild_service_account.id
  included_files  = ["banking-service/**"]
  ignored_files = [
    "banking-service/cloudbuild-db-migrate.yaml",
    "banking-service/cloudbuild-knowledge-catalog-sync.yaml",
    "banking-service/resources/data/fraud_support_guidance.json",
    "banking-service/scripts/sync_fraud_support_guidance.py",
  ]
  filename           = "banking-service/cloudbuild-publish-deploy.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION              = var.region
    _TRIGGER_DEPLOY      = "true"
    _IAM_DBA_USERS       = join(",", [for k, v in local.db_iam_support_members : v.name])
    _IAM_DB_VIEWER_USERS = join(",", [for k, v in local.db_iam_viewer_members : v.name])
  }
}

resource "google_cloudbuild_trigger" "knowledge_catalog_sync_trigger" {
  count    = var.deploy_cloud_build_triggers ? 1 : 0
  name     = "banking-knowledge-catalog-sync"
  location = var.region
  tags     = ["banking-service", "knowledge-catalog", "sync"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
    push {
      branch = local.trigger_by_branch ? var.repo_branch_expression : null
      tag    = local.trigger_by_tag ? var.repo_tag_expression : null
    }
  }

  service_account = google_service_account.cloudbuild_service_account.id
  included_files = [
    "banking-service/cloudbuild-knowledge-catalog-sync.yaml",
    "banking-service/resources/data/fraud_support_guidance.json",
    "banking-service/scripts/sync_fraud_support_guidance.py",
    "banking-service/services/knowledge_catalog.py",
  ]
  filename           = "banking-service/cloudbuild-knowledge-catalog-sync.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION = var.region
  }
}

resource "google_cloudbuild_trigger" "banking_ui_deploy_trigger" {
  count    = var.deploy_cloud_build_triggers ? 1 : 0
  name     = "banking-ui-deployment"
  location = var.region
  tags     = ["banking-ui", "deploy"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
    push {
      branch = local.trigger_by_branch ? var.repo_branch_expression : null
      tag    = local.trigger_by_tag ? var.repo_tag_expression : null
    }
  }

  service_account    = google_service_account.cloudbuild_service_account.id
  included_files     = ["banking-ui/**"]
  filename           = "banking-ui/cloudbuild-publish-deploy.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION         = var.region
    _TRIGGER_DEPLOY = "true"
  }
}

resource "google_cloudbuild_trigger" "iap_login_ui_deploy_trigger" {
  count    = var.deploy_cloud_build_triggers && var.use_external_identities ? 1 : 0
  name     = "iap-login-ui-deployment"
  location = var.region
  tags     = ["iap-login-ui", "deploy"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
    push {
      branch = local.trigger_by_branch ? var.repo_branch_expression : null
      tag    = local.trigger_by_tag ? var.repo_tag_expression : null
    }
  }

  service_account    = google_service_account.cloudbuild_service_account.id
  included_files     = ["iap-login-ui/**"]
  filename           = "iap-login-ui/cloudbuild-publish-deploy.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION         = var.region
    _TRIGGER_DEPLOY = "true"
  }
}

resource "google_cloudbuild_trigger" "banking_ui_crawl_trigger" {
  count    = var.deploy_cloud_build_triggers && var.deploy_cloud_run_services ? 1 : 0
  name     = "banking-ui-crawl"
  location = var.region
  tags     = ["banking-ui", "crawl"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
    push {
      branch = local.trigger_by_branch ? var.repo_branch_expression : null
      tag    = local.trigger_by_tag ? var.repo_tag_expression : null
    }
  }

  service_account    = google_service_account.cloudbuild_crawler_service_account.id
  included_files     = ["scripts/crawl_and_upload/**"]
  filename           = "scripts/crawl_and_upload/cloudbuild-crawl.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _GCS_BUCKET_NAME   = google_storage_bucket.site_crawled_content.name
    _USE_GCP_AUTH      = "true"
    _GCP_AUTH_AUDIENCE = google_cloud_run_v2_service.banking_ui[0].urls[0]
    _SITEMAP_URL       = "${google_cloud_run_v2_service.banking_ui[0].urls[0]}/sitemap.xml"
    _SITE_BASE_URL     = "https://${var.custom_domain}"
    _DATA_STORE_ID     = google_discovery_engine_data_store.gcs_site.data_store_id
  }
}

resource "google_cloudbuild_trigger" "credit_support_agent_deploy_trigger" {
  count    = var.deploy_cloud_build_triggers ? 1 : 0
  name     = "credit-support-agent-deployment"
  location = var.region
  tags     = ["credit-support-agent", "deploy"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
    push {
      branch = local.trigger_by_branch ? var.repo_branch_expression : null
      tag    = local.trigger_by_tag ? var.repo_tag_expression : null
    }
  }

  service_account    = google_service_account.cloudbuild_service_account.id
  included_files     = ["adk-agent/credit-support-agent/**"]
  filename           = "adk-agent/credit-support-agent/cloudbuild-deploy.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION         = var.region
    _TRIGGER_DEPLOY = "true"
  }
}

resource "google_cloudbuild_trigger" "data_generator_deploy_trigger" {
  count    = var.deploy_cloud_build_triggers ? 1 : 0
  name     = "data-generator-deployment"
  location = var.region
  tags     = ["data-generator", "deploy"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
    push {
      branch = local.trigger_by_branch ? var.repo_branch_expression : null
      tag    = local.trigger_by_tag ? var.repo_tag_expression : null
    }
  }

  service_account    = google_service_account.cloudbuild_service_account.id
  included_files     = ["data-generator/**"]
  filename           = "data-generator/cloudbuild-publish-deploy.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION         = var.region
    _TRIGGER_DEPLOY = "true"
  }
}

resource "google_cloudbuild_trigger" "lakehouse_reconcile_image_trigger" {
  count    = var.deploy_cloud_build_triggers ? 1 : 0
  name     = "lakehouse-view-reconcile-image"
  location = var.region
  tags     = ["lakehouse", "bigquery", "deploy"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
    push {
      branch = local.trigger_by_branch ? var.repo_branch_expression : null
      tag    = local.trigger_by_tag ? var.repo_tag_expression : null
    }
  }

  service_account = google_service_account.cloudbuild_service_account.id
  included_files = [
    "deployment/lakehouse-reconcile/**",
    "deployment/bigquery/analytics_curated/**",
    "scripts/datastream/reconcile_lakehouse_views.py",
  ]
  filename           = "deployment/lakehouse-reconcile/cloudbuild.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION = var.region
  }
}

resource "google_cloudbuild_trigger" "db_migration_manual_trigger" {
  count    = var.deploy_cloud_build_triggers ? 1 : 0
  name     = "run-db-migration"
  location = var.region
  tags     = ["banking-db-migration", "manual"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
  }

  service_account    = google_service_account.cloudbuild_service_account.id
  filename           = "banking-service/cloudbuild-db-migrate.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION = var.region
  }
}

resource "google_cloudbuild_trigger" "terraform_apply_trigger" {
  count    = var.deploy_cloud_build_triggers ? 1 : 0
  name     = "terraform-apply"
  location = var.region
  tags     = ["terraform", "apply"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
  }

  approval_config {
    approval_required = true
  }

  service_account    = google_service_account.cloudbuild_terraform_service_account.id
  included_files     = ["deployment/terraform/**"]
  filename           = "deployment/cloud_build/cloudbuild-tf-apply.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION = var.region
  }
}

resource "google_cloudbuild_trigger" "terraform_plan_trigger" {
  count    = var.deploy_cloud_build_triggers ? 1 : 0
  name     = "terraform-plan"
  location = var.region
  tags     = ["terraform", "plan"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
  }

  service_account    = google_service_account.cloudbuild_terraform_service_account.id
  included_files     = ["deployment/terraform/**"]
  filename           = "deployment/cloud_build/cloudbuild-tf-plan.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION = var.region
  }
}

resource "google_cloudbuild_trigger" "real_time_analytics_agent_deploy_trigger" {
  count    = var.deploy_cloud_build_triggers ? 1 : 0
  name     = "real-time-analytics-agent-deploy"
  location = var.region
  tags     = ["data-agent", "analytics", "manual"]

  repository_event_config {
    repository = google_cloudbuildv2_repository.fsi_gecx_bundle[0].id
  }

  service_account    = google_service_account.cloudbuild_service_account.id
  filename           = "deployment/cloud_build/cloudbuild-data-agent-deploy.yaml"
  include_build_logs = "INCLUDE_BUILD_LOGS_WITH_STATUS"

  substitutions = {
    _REGION = var.region
  }

  depends_on = [
    google_project_service.cloudaicompanion_googleapis_com,
    google_project_service.geminidataanalytics_googleapis_com,
    google_project_iam_member.cloudbuild_sa_data_agent_creator,
    google_project_iam_member.cloudbuild_sa_data_agent_editor,
    google_bigquery_dataset_iam_member.cloudbuild_sa_agent_analytics_metadata_viewer,
    google_bigquery_dataset_iam_member.cloudbuild_sa_agent_compliance_metadata_viewer,
    google_bigquery_dataset_iam_member.cloudbuild_sa_agent_cdc_metadata_viewer,
    google_bigquery_dataset_iam_member.cloudbuild_sa_agent_analytics_data_viewer,
    google_bigquery_dataset_iam_member.cloudbuild_sa_agent_compliance_data_viewer,
    google_bigquery_dataset_iam_member.cloudbuild_sa_agent_cdc_data_viewer,
  ]
}
