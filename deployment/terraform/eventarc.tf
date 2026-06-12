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

resource "google_pubsub_topic" "artifact_processing" {
  name       = "banking-artifact-processing"
  depends_on = [google_project_service.pubsub_googleapis_com]
}

resource "google_pubsub_topic" "artifact_dlq" {
  name       = "banking-artifact-dlq"
  depends_on = [google_project_service.pubsub_googleapis_com]
}

resource "google_pubsub_subscription" "artifact_processing_sub" {
  name  = "banking-artifact-processing-sub"
  topic = google_pubsub_topic.artifact_processing.name

  ack_deadline_seconds = 600 # 10-minute timeout for long-running Gemini extractions

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s" # Exponential backoff up to 10 mins
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.artifact_dlq.id
    max_delivery_attempts = 5
  }
}

resource "google_service_account" "eventarc_sa" {
  account_id   = "banking-eventarc-sa"
  display_name = "Eventarc Artifact Processing Service Account"
}

resource "google_cloud_run_service_iam_member" "eventarc_invoker" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  service  = google_cloud_run_v2_service.banking_service[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.eventarc_sa.email}"
}

resource "google_project_iam_member" "eventarc_event_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.eventarc_sa.email}"
}

resource "time_sleep" "wait_for_pubsub_propagation" {
  depends_on = [
    google_project_iam_member.gcs_pubsub_publisher
  ]
  create_duration = "30s"
}

resource "google_eventarc_trigger" "artifact_finalized_trigger" {
  name     = "banking-artifact-finalized-trigger"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }
  matching_criteria {
    attribute = "bucket"
    value     = google_storage_bucket.banking_interaction_artifacts.name
  }

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.banking_service[0].name
      path    = "/internal/process-document"
      region  = var.region
    }
  }

  service_account = google_service_account.eventarc_sa.email
  depends_on = [
    google_project_service.eventarc_googleapis_com,
    google_project_service_identity.eventarc_sa,
    google_cloud_run_service_iam_member.eventarc_invoker,
    time_sleep.wait_for_pubsub_propagation
  ]
}
