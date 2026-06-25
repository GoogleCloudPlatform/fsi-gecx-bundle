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

    # 1. Enable Data API for Conversational Analytics
    data_api_access = "ALLOW_DATA_API"

    # 2. Enable Knowledge Catalog (Dataplex) Integration
    enable_dataplex_integration = true

    pricing_plan                = "PER_USE"
    tier                        = "db-custom-1-3840"
    deletion_protection_enabled = true
  }

  deletion_protection = true
  root_password       = random_password.postgres_root_password.result

  depends_on = [
    google_project_service.sqladmin_googleapis_com,
    google_project_service.servicenetworking_googleapis_com,
    google_service_networking_connection.private_vpc_connection
  ]
}

resource "random_password" "postgres_root_password" {
  length  = 16
  special = false
}

# BigQuery Connection user with password
resource "google_sql_user" "banking_bq_connector" {
  name     = "banking_bq_connector"
  instance = google_sql_database_instance.banking_data.name
  password = random_password.banking_bq_connector_password.result
}

resource "random_password" "banking_bq_connector_password" {
  length  = 16
  special = false
}

resource "google_sql_database" "banking" {
  name            = "banking"
  instance        = google_sql_database_instance.banking_data.name
  deletion_policy = "ABANDON"
}

resource "google_sql_user" "banking_db_migration_iam_user" {
  name     = replace(google_service_account.banking_db_migration_service_account.email, ".gserviceaccount.com", "")
  instance = google_sql_database_instance.banking_data.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

resource "google_sql_user" "banking_service_sa_iam_user" {
  name     = replace(google_service_account.banking_service_account.email, ".gserviceaccount.com", "")
  instance = google_sql_database_instance.banking_data.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

locals {
  db_iam_support_members = {
    for member in concat(var.database_iam_support_users, ["user:${data.google_client_openid_userinfo.me.email}"]) :
    member => {
      name = split(":", member)[1]
      type = split(":", member)[0] == "user" ? "CLOUD_IAM_USER" : (
        split(":", member)[0] == "group" ? "CLOUD_IAM_GROUP" : "CLOUD_IAM_SERVICE_ACCOUNT"
      )
    }
  }
}

resource "google_sql_user" "database_iam_support_users" {
  for_each = local.db_iam_support_members
  name     = each.value.name
  instance = google_sql_database_instance.banking_data.name
  type     = each.value.type
}
