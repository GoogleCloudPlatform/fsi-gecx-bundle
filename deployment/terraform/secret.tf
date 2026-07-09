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

resource "google_secret_manager_secret" "postgres_banking_root_password" {
  secret_id = "postgres_banking_root_password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "postgres_banking_root_password_version" {
  secret      = google_secret_manager_secret.postgres_banking_root_password.id
  secret_data = random_password.postgres_root_password.result
}

resource "google_secret_manager_secret" "postgres_banking_bq_connector_password" {
  secret_id = "postgres_banking_bq_connector_password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "postgres_banking_bq_connector_password_version" {
  secret      = google_secret_manager_secret.postgres_banking_bq_connector_password.id
  secret_data = random_password.banking_bq_connector_password.result
}

data "google_secret_manager_secret_version_access" "iap_client_id" {
  secret  = "iap-client-id"
  version = "latest"
}

data "google_secret_manager_secret_version_access" "iap_client_secret" {
  secret  = "iap-client-secret"
  version = "latest"
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

resource "google_secret_manager_secret" "card_network_switch_token" {
  secret_id = "card-network-switch-token"
  replication {
    auto {}
  }
}

resource "random_password" "card_network_switch_token" {
  length  = 32
  special = false
}

resource "google_secret_manager_secret_version" "card_network_switch_token_version" {
  secret      = google_secret_manager_secret.card_network_switch_token.id
  secret_data = random_password.card_network_switch_token.result
}

data "external" "database_iam_support_users" {
  program = ["bash", "${path.module}/scripts/get_secret_safe.sh", "database-iam-support-users", var.project_id, "true"]
}

# Rename the secret
data "external" "iam_console_viewers" {
  program = ["bash", "${path.module}/scripts/get_secret_safe.sh", "iam_console_viewers", var.project_id, "true"]
}

data "external" "additional_cloud_run_iap_members" {
  program = ["bash", "${path.module}/scripts/get_secret_safe.sh", "additional-cloud-run-iap-members", var.project_id, "true"]
}

locals {
  database_iam_support_users_raw = data.external.database_iam_support_users.result.secret_data
  database_iam_support_users     = compact([for s in split(",", local.database_iam_support_users_raw) : trimspace(s)])

  iam_console_viewers_raw = data.external.iam_console_viewers.result.secret_data
  iam_console_viewers     = compact([for s in split(",", local.iam_console_viewers_raw) : trimspace(s)])

  additional_cloud_run_iap_members_raw = data.external.additional_cloud_run_iap_members.result.secret_data
  additional_cloud_run_iap_members     = compact([for s in split(",", local.additional_cloud_run_iap_members_raw) : trimspace(s)])
}
