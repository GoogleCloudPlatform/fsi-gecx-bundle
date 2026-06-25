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

resource "google_storage_bucket" "banking_interaction_artifacts" {
  name                        = "${var.project_id}_banking-interaction-artifacts"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  cors {
    origin          = ["http://localhost:5173", "https://${var.custom_domain}"]
    method          = ["GET", "OPTIONS", "PUT"]
    response_header = ["Content-Type", "Authorization"]
    max_age_seconds = 3600
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket" "ccai_insights_artifacts" {
  name                        = "${var.project_id}_ccai-insights-artifacts"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket" "site_crawled_content" {
  name                        = "${var.project_id}_site-crawled-content"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket" "iceberg_warehouse" {
  name                        = "${var.project_id}_iceberg-warehouse"
  location                    = "US"
  uniform_bucket_level_access = true
  force_destroy               = true
}
