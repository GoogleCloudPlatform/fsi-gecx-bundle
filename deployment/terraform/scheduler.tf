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
  description      = "Trigger steady lightweight synthetic card activity"
  schedule         = var.data_generator_cron_schedule
  time_zone        = "Etc/UTC"
  attempt_deadline = var.data_generator_request_timeout
  region           = var.region

  pubsub_target {
    topic_name = google_pubsub_topic.data_generator_trigger.id
    data       = base64encode("{}")
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

resource "google_cloud_scheduler_job" "lakehouse_view_reconcile_daily" {
  count            = var.deploy_cloud_run_services ? 1 : 0
  name             = "lakehouse-view-reconcile-daily"
  description      = "Run idempotent Lakehouse Silver view reconciliation once daily"
  schedule         = "17 10 * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "120s"
  region           = var.region

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${data.google_project.project.project_id}/jobs/${google_cloud_run_v2_job.lakehouse_view_reconcile[0].name}:run"

    headers = {
      "Content-Type" = "application/json"
    }

    body = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.lakehouse_reconcile_service_account.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_project_service.cloudscheduler_googleapis_com,
    google_cloud_run_v2_job.lakehouse_view_reconcile,
    google_project_iam_member.lakehouse_reconcile_sa_run_developer,
  ]
}

resource "google_cloud_scheduler_job" "fraud_alert_lifecycle" {
  count            = var.deploy_cloud_run_services ? 1 : 0
  name             = "fraud-alert-lifecycle"
  description      = "Expire stale open synthetic fraud alerts when no customer response arrives"
  schedule         = var.fraud_alert_lifecycle_schedule
  time_zone        = "Etc/UTC"
  attempt_deadline = "120s"
  region           = var.region

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${data.google_project.project.project_id}/jobs/${google_cloud_run_v2_job.fraud_alert_lifecycle[0].name}:run"

    headers = {
      "Content-Type" = "application/json"
    }

    body = base64encode("{}")

    oauth_token {
      service_account_email = google_service_account.banking_service_account.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_project_service.cloudscheduler_googleapis_com,
    google_cloud_run_v2_job.fraud_alert_lifecycle,
    google_project_iam_member.banking_service_sa_run_developer,
  ]
}

resource "google_cloud_tasks_queue" "data_generator_synthetic_schedule" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "data-generator-synthetic-schedule"
  location = var.region

  rate_limits {
    max_dispatches_per_second = 10
    max_concurrent_dispatches = 5
  }

  retry_config {
    max_attempts  = 5
    min_backoff   = "5s"
    max_backoff   = "300s"
    max_doublings = 5
  }

  depends_on = [
    google_project_service.cloudtasks_googleapis_com
  ]
}

resource "google_cloud_scheduler_job" "audit_outbox_relay" {
  count            = var.deploy_cloud_run_services ? 1 : 0
  name             = "audit-outbox-relay"
  description      = "Publish a bounded batch of committed audit outbox rows"
  schedule         = var.audit_relay_schedule
  time_zone        = "Etc/UTC"
  attempt_deadline = "300s"
  region           = var.region

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${data.google_project.project.project_id}/jobs/${google_cloud_run_v2_job.audit_outbox_relay[0].name}:run"
    headers = {
      "Content-Type" = "application/json"
    }
    body = base64encode("{}")
    oauth_token {
      service_account_email = google_service_account.audit_outbox_relay_service_account.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_project_service.cloudscheduler_googleapis_com,
    google_cloud_run_v2_job.audit_outbox_relay,
    google_cloud_run_v2_job_iam_member.audit_relay_scheduler_invokes_job,
  ]
}
