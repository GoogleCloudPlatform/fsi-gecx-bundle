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

  lifecycle {
    ignore_changes = [
      attempt_deadline
    ]
  }

  depends_on = [
    google_project_service.cloudscheduler_googleapis_com
  ]
}
