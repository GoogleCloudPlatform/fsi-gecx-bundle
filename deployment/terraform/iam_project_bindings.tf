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

resource "google_project_iam_member" "bq_connection_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_bigquery_connection.banking_data_postgres_connection.cloud_sql[0].service_account_id}"
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

resource "google_project_iam_member" "banking_service_sa_spanner_user" {
  project = data.google_project.project.project_id
  role    = "roles/spanner.databaseUser"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "datagen_sa_spanner_user" {
  project = data.google_project.project.project_id
  role    = "roles/spanner.databaseUser"
  member  = "serviceAccount:${google_service_account.data_generator_service_account.email}"
}

resource "google_project_iam_member" "datagen_sa_bq_job_user" {
  project = data.google_project.project.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.data_generator_service_account.email}"
}

resource "google_project_iam_member" "developer_cloudsql_client" {
  project = data.google_project.project.project_id
  role    = "roles/cloudsql.client"
  member  = "user:${data.google_client_openid_userinfo.me.email}"
}

resource "google_project_iam_member" "developer_cloudsql_instance_user" {
  project = data.google_project.project.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "user:${data.google_client_openid_userinfo.me.email}"
}

resource "google_project_iam_member" "banking_service_sa_cloudsql_client" {
  project = data.google_project.project.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "banking_service_sa_cloudsql_instance_user" {
  project = data.google_project.project.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "banking_migration_sa_cloudsql_client" {
  project = data.google_project.project.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.banking_db_migration_service_account.email}"
}

resource "google_project_iam_member" "banking_migration_sa_cloudsql_instance_user" {
  project = data.google_project.project.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.banking_db_migration_service_account.email}"
}

resource "google_project_iam_member" "ledger_sa_cloudsql_client" {
  project = data.google_project.project.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.ledger_service_account.email}"
}

resource "google_project_iam_member" "ledger_sa_cloudsql_instance_user" {
  project = data.google_project.project.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.ledger_service_account.email}"
}

resource "google_project_iam_member" "kyc_sa_cloudsql_client" {
  project = data.google_project.project.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.kyc_service_account.email}"
}

resource "google_project_iam_member" "kyc_sa_cloudsql_instance_user" {
  project = data.google_project.project.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.kyc_service_account.email}"
}

resource "google_project_iam_member" "banking_migration_sa_log_writer" {
  project = data.google_project.project.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.banking_db_migration_service_account.email}"
}

resource "google_project_iam_member" "database_iam_support_instance_users" {
  for_each = local.db_iam_support_members
  project  = data.google_project.project.project_id
  role     = "roles/cloudsql.instanceUser"
  member   = each.key
}

resource "google_project_iam_member" "database_iam_support_viewers" {
  for_each = local.db_iam_support_members
  project  = data.google_project.project.project_id
  role     = "roles/cloudsql.viewer"
  member   = each.key
}

resource "google_project_iam_member" "cloudbuild_sa_bq_job_user" {
  project = data.google_project.project.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"
}
