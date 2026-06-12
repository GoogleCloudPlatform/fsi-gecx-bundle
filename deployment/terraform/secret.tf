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

data "google_secret_manager_secret_version_access" "github_token_secret_version" {
  count      = var.deploy_cloud_build_triggers ? 1 : 0
  secret     = var.github_oauth_token_secret_name
  depends_on = [google_project_service.secretmanager_googleapis_com]
}

resource "google_secret_manager_secret" "postgres_banking_password" {
  secret_id = "postgres_banking_password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "postgres_banking_password_version" {
  secret      = google_secret_manager_secret.postgres_banking_password.id
  secret_data = random_password.banking_password.result
}

resource "google_secret_manager_secret" "livekit_api_key" {
  secret_id = "livekit-api-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "livekit_api_secret" {
  secret_id = "livekit-api-secret"
  replication {
    auto {}
  }
}

# Generate secure random API credentials at deployment time
resource "random_password" "livekit_api_key" {
  length  = 16
  special = false
}

resource "random_password" "livekit_api_secret" {
  length  = 32
  special = false
}

resource "google_secret_manager_secret_version" "livekit_api_key_version" {
  secret      = google_secret_manager_secret.livekit_api_key.id
  secret_data = random_password.livekit_api_key.result
}

resource "google_secret_manager_secret_version" "livekit_api_secret_version" {
  secret      = google_secret_manager_secret.livekit_api_secret.id
  secret_data = random_password.livekit_api_secret.result
}



