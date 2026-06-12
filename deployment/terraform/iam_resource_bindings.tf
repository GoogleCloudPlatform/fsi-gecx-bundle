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

resource "google_secret_manager_secret_iam_member" "github_token_secret_accessor" {
  count     = var.deploy_cloud_build_triggers ? 1 : 0
  secret_id = data.google_secret_manager_secret_version_access.github_token_secret_version[0].name
  role      = "roles/secretmanager.secretAccessor"
  member    = local.legacy_cloudbuild_service_account

  lifecycle {
    ignore_changes = [
      secret_id
    ]
  }

  depends_on = [google_project_service.secretmanager_googleapis_com]
}

resource "google_artifact_registry_repository_iam_member" "cloudbuild_sa_fsi_gecx_bundle_artifact_writer" {
  repository = google_artifact_registry_repository.fsi_gecx_bundle.id
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"
}

resource "google_artifact_registry_repository_iam_member" "cloudbuild_sa_fsi_gecx_bundle_artifact_reader" {
  repository = google_artifact_registry_repository.fsi_gecx_bundle.id
  location   = var.region
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.cloudbuild_service_account.email}"
}

resource "google_cloud_run_service_iam_member" "banking_service_iap_invoker_role" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  service  = google_cloud_run_v2_service.banking_service[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = local.iap_service_account
}

resource "google_cloud_run_service_iam_member" "banking_ui_iap_invoker_role" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  service  = google_cloud_run_v2_service.banking_ui[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = local.iap_service_account
}

resource "google_cloud_run_service_iam_member" "banking_service_invokes_voice_agent" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  service  = google_cloud_run_v2_service.credit_support_agent[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_cloud_run_service_iam_member" "banking_ui_cloudbuild_crawler_invoker_role" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  service  = google_cloud_run_v2_service.banking_ui[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.cloudbuild_crawler_service_account.email}"
}

resource "google_cloud_run_service_iam_member" "iap_login_ui_public_invoker" {
  count    = var.deploy_cloud_run_services && var.use_external_identities ? 1 : 0
  service  = google_cloud_run_v2_service.iap_login_ui[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}


locals {
  cloud_run_iap_members = concat([
    "user:erikvoit@gcp.solutions"
  ], var.additional_cloud_run_iap_members)
}

resource "google_iap_web_backend_service_iam_member" "banking_service_access" {
  for_each            = var.deploy_cloud_run_services ? toset(local.cloud_run_iap_members) : toset([])
  web_backend_service = google_compute_backend_service.service_backend[0].name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.key

  depends_on = [
    google_project_service.iap_googleapis_com
  ]
}

resource "google_iap_web_backend_service_iam_member" "banking_ui_access" {
  for_each            = var.deploy_cloud_run_services ? toset(local.cloud_run_iap_members) : toset([])
  web_backend_service = google_compute_backend_service.ui_backend[0].name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.key

  depends_on = [
    google_project_service.iap_googleapis_com
  ]
}

resource "google_storage_bucket_iam_member" "banking_service_account_bucket_admin" {
  bucket = google_storage_bucket.banking_interaction_artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_storage_bucket_iam_member" "ccai_insights_service_account_bucket_admin" {
  bucket = google_storage_bucket.ccai_insights_artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ccai_insights_service_account.email}"
}

resource "google_secret_manager_secret_iam_member" "banking_service_ccai_secret_accessor" {
  secret_id = "ccai-company-secret"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_secret_manager_secret_iam_member" "banking_service_iap_client_secret_accessor" {
  secret_id = "iap-client-secret"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_secret_manager_secret_iam_member" "banking_service_iap_client_id_accessor" {
  secret_id = "iap-client-id"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_secret_manager_secret_iam_member" "ces_secret_accessor" {
  secret_id = "iap-client-secret"
  role      = "roles/secretmanager.secretAccessor"
  member    = local.ces_service_account

  depends_on = [google_project_service.ces_googleapis_com]
}

resource "google_bigquery_dataset_iam_member" "banking_service_account_bq_data_editor" {
  project    = data.google_project.project.project_id
  dataset_id = google_bigquery_dataset.banking.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.banking_service_account.email}"
}

data "google_storage_project_service_account" "gcs_sa" {}

data "google_bigquery_default_service_account" "bq_sa" {}

resource "google_kms_crypto_key_iam_member" "gcs_kms_binding" {
  crypto_key_id = google_kms_crypto_key.banking_cmek_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${data.google_storage_project_service_account.gcs_sa.email_address}"
}

resource "google_kms_crypto_key_iam_member" "bq_kms_binding" {
  crypto_key_id = google_kms_crypto_key.banking_cmek_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${data.google_bigquery_default_service_account.bq_sa.email}"
}

resource "google_kms_crypto_key_iam_member" "docai_kms_binding" {
  crypto_key_id = google_kms_crypto_key.docai_cmek_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_project_service_identity.docai_sa.email}"
}


resource "google_storage_bucket_iam_member" "cloudbuild_crawler_sa_site_crawled_content_writer" {
  bucket = google_storage_bucket.site_crawled_content.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cloudbuild_crawler_service_account.email}"
}

resource "google_storage_bucket_iam_member" "discovery_engine_site_crawled_content_reader" {
  bucket = google_storage_bucket.site_crawled_content.name
  role   = "roles/storage.objectViewer"
  member = local.discovery_engine_service_account
}
