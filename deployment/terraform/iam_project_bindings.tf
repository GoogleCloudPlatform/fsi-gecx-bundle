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

resource "google_project_iam_member" "cloudbuild_sa_log_writer" {
  project = data.google_project.project.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"
}

resource "google_project_iam_member" "cloudbuild_terraform_sa_owner" {
  project = data.google_project.project.project_id
  role    = "roles/owner"
  member  = "serviceAccount:${google_service_account.cloudbuild_terraform_service_account.email}"
}

resource "google_project_iam_member" "cloudbuild_terraform_sa_act_as" {
  project = data.google_project.project.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.cloudbuild_terraform_service_account.email}"
}

# Cloud Build attached service-account credentials cannot directly mint an OIDC
# token. The release controller impersonates its own identity for authenticated
# Cloud Run health probes.
resource "google_service_account_iam_member" "cloudbuild_terraform_sa_token_creator_self" {
  service_account_id = google_service_account.cloudbuild_terraform_service_account.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.cloudbuild_terraform_service_account.email}"
}

resource "google_project_iam_member" "cloudbuild_sa_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"

  depends_on = [google_project_service.run_googleapis_com]
}

resource "google_project_iam_member" "cloudbuild_sa_act_as" {
  project = data.google_project.project.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"
}

resource "google_project_iam_member" "ccai_virtual_agent_dialogflow_admin" {
  project = data.google_project.project.project_id
  role    = "roles/dialogflow.admin"
  member  = "serviceAccount:${google_service_account.ccai_virtual_agent_service_account.email}"
}

resource "google_project_iam_member" "ccai_agent_assist_dialogflow_admin" {
  project = data.google_project.project.project_id
  role    = "roles/dialogflow.admin"
  member  = "serviceAccount:${google_service_account.ccai_agent_assist_service_account.email}"
}

resource "google_project_iam_member" "banking_service_sa_bq_job_user" {
  project = data.google_project.project.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "banking_service_sa_ai_user" {
  project = data.google_project.project.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "banking_service_sa_monitoring_viewer" {
  project = data.google_project.project.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "banking_service_sa_dialogflow_client" {
  project = data.google_project.project.project_id
  role    = "roles/dialogflow.client"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "banking_service_sa_ces_client" {
  project = data.google_project.project.project_id
  role    = "roles/ces.client"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

# Required to signBlob
resource "google_service_account_iam_member" "banking_service_sa_token_creator_self" {
  service_account_id = google_service_account.banking_service_account.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "cloudbuild_sa_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"

  depends_on = [google_project_service.run_googleapis_com]
}

resource "google_project_iam_member" "cloudbuild_crawler_sa_worker_pool_user" {
  project = var.project_id
  role    = "roles/cloudbuild.workerPoolUser"
  member  = "serviceAccount:${google_service_account.cloudbuild_crawler_service_account.email}"
}

resource "google_project_iam_member" "cloudbuild_crawler_sa_log_writer" {
  project = data.google_project.project.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloudbuild_crawler_service_account.email}"
}

resource "google_service_account_iam_member" "cloudbuild_crawler_sa_id_token_creator" {
  service_account_id = google_service_account.cloudbuild_crawler_service_account.name
  role               = "roles/iam.serviceAccountOpenIdTokenCreator"
  member             = "serviceAccount:${google_service_account.cloudbuild_crawler_service_account.email}"
}

resource "google_project_iam_member" "cloudbuild_crawler_sa_discovery_engine_admin" {
  project = data.google_project.project.project_id
  role    = "roles/discoveryengine.admin"
  member  = "serviceAccount:${google_service_account.cloudbuild_crawler_service_account.email}"
}

resource "google_project_iam_member" "discovery_engine_sa_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = local.discovery_engine_service_account
}

resource "google_project_iam_member" "banking_service_sa_discovery_engine_viewer" {
  project = data.google_project.project.project_id
  role    = "roles/discoveryengine.viewer"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "cloudbuild_sa_build_runner" {
  project = data.google_project.project.project_id
  role    = google_project_iam_custom_role.cloud_build_job_runner.id
  member  = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"
}

resource "google_project_iam_member" "knowledge_catalog_sync_sa_catalog_editor" {
  project = data.google_project.project.project_id
  role    = "roles/dataplex.catalogEditor"
  member  = "serviceAccount:${google_service_account.knowledge_catalog_sync_service_account.email}"
}

resource "google_project_iam_member" "banking_service_sa_fcm_admin" {
  project = data.google_project.project.project_id
  role    = "roles/firebasecloudmessaging.admin"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "gcs_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs_sa.email_address}"
}

resource "google_project_iam_member" "bq_connection_alloydb_client" {
  project = var.project_id
  role    = "roles/alloydb.client"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-bigqueryconnection.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "jump_instance_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.jump_instance_service_account.email}"
}

resource "google_project_iam_member" "jump_instance_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.jump_instance_service_account.email}"
}

resource "google_project_iam_member" "datagen_sa_bq_job_user" {
  project = data.google_project.project.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.data_generator_service_account.email}"
}

resource "google_project_iam_member" "datagen_sa_cloudtasks_enqueuer" {
  project = data.google_project.project.project_id
  role    = "roles/cloudtasks.enqueuer"
  member  = "serviceAccount:${google_service_account.data_generator_service_account.email}"
}

resource "google_service_account_iam_member" "datagen_sa_cloudtasks_oidc_act_as_self" {
  service_account_id = google_service_account.data_generator_service_account.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.data_generator_service_account.email}"
}

resource "google_project_iam_member" "datagen_sa_alloydb_client" {
  project = data.google_project.project.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.data_generator_service_account.email}"
}

resource "google_project_iam_member" "datagen_sa_service_usage_consumer" {
  project = data.google_project.project.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.data_generator_service_account.email}"
}

resource "google_project_iam_member" "developer_alloydb_client" {
  count   = local.primary_developer_iam_member == null ? 0 : 1
  project = data.google_project.project.project_id
  role    = "roles/alloydb.databaseUser"
  member  = local.primary_developer_iam_member
}

resource "google_project_iam_member" "developer_service_usage_consumer" {
  count   = local.primary_developer_iam_member == null ? 0 : 1
  project = data.google_project.project.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.primary_developer_iam_member
}

resource "google_project_iam_member" "additional_developer_alloydb_client" {
  for_each = local.additional_developer_iam_members
  project  = data.google_project.project.project_id
  role     = "roles/alloydb.databaseUser"
  member   = each.value
}

resource "google_project_iam_member" "banking_service_sa_alloydb_client" {
  project = data.google_project.project.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "banking_service_sa_service_usage_consumer" {
  project = data.google_project.project.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "voice_agent_sa_alloydb_client" {
  project = data.google_project.project.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.voice_agent_sa.email}"
}

resource "google_project_iam_member" "voice_agent_sa_service_usage_consumer" {
  project = data.google_project.project.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.voice_agent_sa.email}"
}

resource "google_project_iam_member" "banking_service_sa_run_developer" {
  project = data.google_project.project.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "banking_migration_sa_alloydb_client" {
  project = data.google_project.project.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.banking_db_migration_service_account.email}"
}

resource "google_project_iam_member" "banking_migration_sa_service_usage_consumer" {
  project = data.google_project.project.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.banking_db_migration_service_account.email}"
}

resource "google_project_iam_member" "banking_reset_sa_alloydb_client" {
  project = data.google_project.project.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.banking_db_reset_service_account.email}"
}

resource "google_project_iam_member" "banking_reset_sa_service_usage_consumer" {
  project = data.google_project.project.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.banking_db_reset_service_account.email}"
}

resource "google_project_iam_member" "banking_reset_sa_log_writer" {
  project = data.google_project.project.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.banking_db_reset_service_account.email}"
}

resource "google_project_iam_member" "banking_reset_sa_cloudtasks_queue_admin" {
  project = data.google_project.project.project_id
  role    = "roles/cloudtasks.queueAdmin"
  member  = "serviceAccount:${google_service_account.banking_db_reset_service_account.email}"
}

resource "google_project_iam_member" "audit_relay_sa_alloydb_client" {
  project = data.google_project.project.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.audit_outbox_relay_service_account.email}"
}

resource "google_project_iam_member" "audit_relay_sa_service_usage_consumer" {
  project = data.google_project.project.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.audit_outbox_relay_service_account.email}"
}

resource "google_project_iam_member" "audit_relay_sa_log_writer" {
  project = data.google_project.project.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.audit_outbox_relay_service_account.email}"
}

resource "google_project_iam_member" "ledger_sa_alloydb_client" {
  project = data.google_project.project.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.ledger_service_account.email}"
}

resource "google_project_iam_member" "ledger_sa_service_usage_consumer" {
  project = data.google_project.project.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.ledger_service_account.email}"
}

resource "google_project_iam_member" "kyc_sa_alloydb_client" {
  project = data.google_project.project.project_id
  role    = "roles/alloydb.databaseUser"
  member  = "serviceAccount:${google_service_account.kyc_service_account.email}"
}

resource "google_project_iam_member" "kyc_sa_service_usage_consumer" {
  project = data.google_project.project.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.kyc_service_account.email}"
}

resource "google_project_iam_member" "banking_migration_sa_log_writer" {
  project = data.google_project.project.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.banking_db_migration_service_account.email}"
}

resource "google_project_iam_member" "database_iam_support_database_users" {
  for_each = local.db_iam_support_members
  project  = data.google_project.project.project_id
  role     = "roles/alloydb.databaseUser"
  member   = each.key
}

resource "google_project_iam_member" "database_iam_support_alloydb_viewers" {
  for_each = local.db_iam_support_members
  project  = data.google_project.project.project_id
  role     = "roles/alloydb.viewer"
  member   = each.key
}

resource "google_project_iam_member" "database_iam_support_service_usage_consumers" {
  for_each = local.db_iam_support_members
  project  = data.google_project.project.project_id
  role     = "roles/serviceusage.serviceUsageConsumer"
  member   = each.key
}

resource "google_project_iam_member" "database_iam_viewer_database_users" {
  for_each = local.db_iam_viewer_members
  project  = data.google_project.project.project_id
  role     = "roles/alloydb.databaseUser"
  member   = each.key
}

resource "google_project_iam_member" "database_iam_viewer_service_usage_consumers" {
  for_each = local.db_iam_viewer_members
  project  = data.google_project.project.project_id
  role     = "roles/serviceusage.serviceUsageConsumer"
  member   = each.key
}

resource "google_project_iam_member" "database_iam_viewer_bigquery_connection_users" {
  for_each = local.db_iam_viewer_members
  project  = data.google_project.project.project_id
  role     = "roles/bigquery.connectionUser"
  member   = each.key
}

resource "google_project_iam_member" "cloudbuild_sa_bq_job_user" {
  project = data.google_project.project.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"
}

resource "google_project_iam_member" "cloudbuild_sa_data_agent_creator" {
  project = data.google_project.project.project_id
  role    = "roles/geminidataanalytics.dataAgentCreator"
  member  = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"

  depends_on = [google_project_service.geminidataanalytics_googleapis_com]
}

resource "google_project_iam_member" "cloudbuild_sa_data_agent_editor" {
  project = data.google_project.project.project_id
  role    = "roles/geminidataanalytics.dataAgentEditor"
  member  = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"

  depends_on = [google_project_service.geminidataanalytics_googleapis_com]
}

resource "google_project_iam_member" "cloudbuild_sa_data_catalog_viewer" {
  project = data.google_project.project.project_id
  role    = "roles/datacatalog.viewer"
  member  = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"
}

resource "google_project_iam_member" "lakehouse_reconcile_sa_bq_job_user" {
  project = data.google_project.project.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.lakehouse_reconcile_service_account.email}"
}

resource "google_project_iam_member" "lakehouse_reconcile_sa_datastream_admin" {
  project = data.google_project.project.project_id
  role    = "roles/datastream.admin"
  member  = "serviceAccount:${google_service_account.lakehouse_reconcile_service_account.email}"
}

resource "google_project_iam_member" "lakehouse_reconcile_sa_run_developer" {
  project = data.google_project.project.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.lakehouse_reconcile_service_account.email}"
}

locals {
  demo_viewer_roles      = yamldecode(file("${path.module}/config/demo_viewer_role.yaml")).roles
  viewer_user_roles_list = setproduct(local.iam_console_viewers, local.demo_viewer_roles)
  viewer_user_roles = {
    for pair in local.viewer_user_roles_list : "${pair[0]}_${pair[1]}" => {
      user = pair[0]
      role = pair[1]
    }
  }
}

resource "google_project_iam_member" "demo_user_iam_role" {
  for_each = local.viewer_user_roles
  project  = data.google_project.project.project_id
  role     = each.value.role
  member   = each.value.user
}

resource "google_project_iam_member" "demo_user_custom_role" {
  for_each = toset(local.iam_console_viewers)
  project  = data.google_project.project.project_id
  role     = google_project_iam_custom_role.demo_viewer.id
  member   = each.value
}
