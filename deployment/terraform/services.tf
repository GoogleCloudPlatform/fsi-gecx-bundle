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

resource "google_project_service" "compute_googleapis_com" {
  service            = "compute.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run_googleapis_com" {
  // Do not disable_on_destroy, as this deletes the
  // serverless-robot-prod.iam.gserviceaccount.com SA
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild_googleapis_com" {
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry_googleapis_com" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iam_googleapis_com" {
  service            = "iam.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "iap_googleapis_com" {
  service            = "iap.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "bigquery_googleapis_com" {
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "servicenetworking_googleapis_com" {
  service            = "servicenetworking.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager_googleapis_com" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "containerscanning_googleapis_com" {
  service            = "containerscanning.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "aiplatform_googleapis_com" {
  service            = "aiplatform.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "dialogflow_googleapis_com" {
  service            = "dialogflow.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "certificatemanager_googleapis_com" {
  service            = "certificatemanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "connectors_googleapis_com" {
  service            = "connectors.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "ces_googleapis_com" {
  service            = "ces.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "kms_googleapis_com" {
  service            = "cloudkms.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "eventarc_googleapis_com" {
  service            = "eventarc.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "pubsub_googleapis_com" {
  service            = "pubsub.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "documentai_googleapis_com" {
  service            = "documentai.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "identitytoolkit_googleapis_com" {
  service            = "identitytoolkit.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudfunctions_googleapis_com" {
  service            = "cloudfunctions.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "firebase_googleapis_com" {
  service            = "firebase.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "discoveryengine_googleapis_com" {
  service            = "discoveryengine.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "datacatalog_googleapis_com" {
  service            = "datacatalog.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service_identity" "docai_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "documentai.googleapis.com"
}

resource "google_project_service_identity" "eventarc_sa" {
  provider = google-beta
  project  = var.project_id
  service  = "eventarc.googleapis.com"
}

resource "google_project_service" "osconfig_googleapis_com" {
  service            = "osconfig.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "sqladmin_googleapis_com" {
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "redis_googleapis_com" {
  service            = "redis.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "spanner_googleapis_com" {
  service            = "spanner.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudscheduler_googleapis_com" {
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}
