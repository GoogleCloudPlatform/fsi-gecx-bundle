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

resource "google_redis_instance" "banking" {
  authorized_network = google_compute_network.fsi_gecx_vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  reserved_ip_range  = google_compute_global_address.private_service_access.name

  location_id    = "us-central1-c"
  memory_size_gb = 1
  name           = "banking-cache"

  persistence_config {
    persistence_mode = "DISABLED"
  }

  redis_version = "REDIS_7_2"
  region        = var.region
  tier          = "BASIC"

  auth_enabled            = true
  transit_encryption_mode = "SERVER_AUTHENTICATION"

  read_replicas_mode = "READ_REPLICAS_DISABLED"

  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"

      start_time {
        hours = 2
      }
    }
  }

  depends_on = [
    google_project_service.redis_googleapis_com,
    google_service_networking_connection.private_vpc_connection
  ]
}

resource "google_secret_manager_secret" "redis_password" {
  secret_id = "redis-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager_googleapis_com]
}

resource "google_secret_manager_secret_iam_member" "redis_password_accessor" {
  secret_id = google_secret_manager_secret.redis_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_secret_manager_secret_version" "redis_password_version" {
  secret      = google_secret_manager_secret.redis_password.id
  secret_data = google_redis_instance.banking.auth_string
}

resource "google_secret_manager_secret" "redis_ca_cert" {
  secret_id = "redis-ca-cert"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager_googleapis_com]
}

resource "google_secret_manager_secret_version" "redis_ca_cert_version" {
  secret      = google_secret_manager_secret.redis_ca_cert.id
  secret_data = google_redis_instance.banking.server_ca_certs[0].cert
}
