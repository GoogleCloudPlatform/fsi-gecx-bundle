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

resource "google_pubsub_topic" "data_generator_trigger" {
  name       = "data-generator-trigger"
  depends_on = [google_project_service.pubsub_googleapis_com]
}

resource "google_cloud_scheduler_job" "data_generator_cron" {
  name             = "data-generator-cron"
  description      = "Trigger synthetic data generation every 1 minute"
  schedule         = "*/1 * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "320s"
  region           = var.region

  pubsub_target {
    topic_name = google_pubsub_topic.data_generator_trigger.id
    data       = base64encode("{\"num_accounts\": 2, \"transactions_per_account\": 5}")
  }

  depends_on = [
    google_project_service.cloudscheduler_googleapis_com
  ]
}

resource "google_cloud_run_service_iam_member" "eventarc_data_generator_invoker" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  service  = google_cloud_run_v2_service.data_generator[0].name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.eventarc_sa.email}"
}

resource "google_eventarc_trigger" "data_generator" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "data-generator-trigger"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.data_generator[0].name
      path    = "/generate"
      region  = var.region
    }
  }

  transport {
    pubsub {
      topic = google_pubsub_topic.data_generator_trigger.id
    }
  }

  service_account = google_service_account.eventarc_sa.email

  depends_on = [
    google_project_service.eventarc_googleapis_com,
    google_project_service_identity.eventarc_sa,
    google_cloud_run_service_iam_member.eventarc_data_generator_invoker
  ]
}
