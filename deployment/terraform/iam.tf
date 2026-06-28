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
  legacy_cloudbuild_service_account = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
  iap_service_account               = "serviceAccount:${google_project_service_identity.iap_sa.email}" # "serviceAccount:service-${data.google_project.project.number}@gcp-sa-iap.iam.gserviceaccount.com"
  ces_service_account               = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-ces.iam.gserviceaccount.com"
  discovery_engine_service_account  = "serviceAccount:${google_project_service_identity.discoveryengine_sa.email}" # "serviceAccount:service-${data.google_project.project.number}@gcp-sa-discoveryengine.iam.gserviceaccount.com"
  identity_toolkit_service_account  = "serviceAccount:${google_project_service_identity.identitytoolkit_sa.email}"
}

resource "google_service_account" "cloudbuild_service_account" {
  account_id   = "cloudbuild-sa"
  display_name = "Cloud Build Service Account"

  lifecycle {
    ignore_changes = [
      description,
      display_name
    ]
  }
}

resource "google_service_account" "cloudbuild_crawler_service_account" {
  account_id   = "cloudbuild-crawler-sa"
  display_name = "Cloud Build Crawler Service Account"

  lifecycle {
    ignore_changes = [
      description,
      display_name
    ]
  }
}

resource "google_service_account" "banking_service_account" {
  account_id   = "banking-service-sa"
  display_name = "Banking Service Account"

  lifecycle {
    ignore_changes = [
      description,
      display_name
    ]
  }
}

resource "google_service_account" "banking_db_migration_service_account" {
  account_id   = "banking-db-migration-sa"
  display_name = "Banking DB Migration Service Account"

  lifecycle {
    ignore_changes = [
      description,
      display_name
    ]
  }
}

resource "google_service_account" "ledger_service_account" {
  account_id   = "ledger-service-sa"
  display_name = "Least Privilege Ledger Schema Service Account"
}

resource "google_service_account" "kyc_service_account" {
  account_id   = "kyc-service-sa"
  display_name = "Least Privilege KYC Schema Service Account"
}

resource "google_service_account" "ccai_insights_service_account" {
  account_id   = "ccai-insights-sa"
  display_name = "CCAI Insights Service Account"

  lifecycle {
    ignore_changes = [
      description,
      display_name
    ]
  }
}

resource "google_service_account" "ccai_virtual_agent_service_account" {
  account_id   = "ccai-virtual-agent-sa"
  display_name = "CCAI Virual Agent Service Account"

  lifecycle {
    ignore_changes = [
      description,
      display_name
    ]
  }
}

resource "google_service_account" "ccai_agent_assist_service_account" {
  account_id   = "ccai-agent-assist-sa"
  display_name = "CCAI Agent Assist Service Account"

  lifecycle {
    ignore_changes = [
      description,
      display_name
    ]
  }
}

resource "google_service_account" "jump_instance_service_account" {
  account_id   = "jump-instance-sa"
  display_name = "Jump Instance Service Account"

  lifecycle {
    ignore_changes = [
      description,
      display_name
    ]
  }
}

resource "google_project_service_identity" "iap_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "iap.googleapis.com"
}

resource "google_project_service_identity" "identitytoolkit_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "identitytoolkit.googleapis.com"
}

resource "google_project_service_identity" "ces_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "ces.googleapis.com"
}

resource "google_project_service_identity" "discoveryengine_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "discoveryengine.googleapis.com"
}

data "google_compute_default_service_account" "default" {
}

resource "google_service_account" "data_generator_service_account" {
  account_id   = "datagen-service-sa"
  display_name = "Data Generator Service Account"

  lifecycle {
    ignore_changes = [
      description,
      display_name
    ]
  }
}
