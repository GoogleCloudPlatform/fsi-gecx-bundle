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

resource "google_sql_database_instance" "banking_data" {
  database_version = "POSTGRES_18"
  name             = "banking-data"
  region           = var.region

  settings {
    edition           = "ENTERPRISE"
    activation_policy = "ALWAYS"
    availability_type = "ZONAL"
    maintenance_window {
      #      Saturday 10pm ET = Sunday 2AM UTC
      day  = 7
      hour = 3
    }

    backup_configuration {
      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }

      enabled                        = true
      location                       = "us"
      point_in_time_recovery_enabled = true
      start_time                     = "02:00"
      transaction_log_retention_days = 7
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    disk_autoresize       = true
    disk_autoresize_limit = 0
    disk_size             = 10
    disk_type             = "PD_SSD"

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = true
    }

    ip_configuration {
      # For using CloudSQL Proxy need this external IP to be true
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.fsi_gecx_vpc.id
      enable_private_path_for_google_cloud_services = true
      ssl_mode                                      = "ENCRYPTED_ONLY"
      authorized_networks {
        # https://docs.cloud.google.com/data-studio/connect-to-postgresql#firewall_and_database_access
        name  = "Looker Studio"
        value = "142.251.74.0/23"
      }
    }

    location_preference {
      zone = "us-central1-c"
    }

    pricing_plan                = "PER_USE"
    tier                        = "db-custom-1-3840"
    deletion_protection_enabled = true
  }

  deletion_protection = true
  root_password       = random_password.banking_password.result

  depends_on = [
    google_project_service.sqladmin_googleapis_com,
    google_project_service.servicenetworking_googleapis_com
  ]
}

resource "google_sql_user" "banking_user" {
  name     = "banking"
  instance = google_sql_database_instance.banking_data.name
  password = random_password.banking_password.result
}

resource "google_sql_database" "banking" {
  name            = "banking"
  instance        = google_sql_database_instance.banking_data.name
  deletion_policy = "ABANDON"
}

resource "random_password" "banking_password" {
  length  = 16
  special = false
}
