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

resource "google_bigquery_dataset" "banking" {
  dataset_id                  = "banking"
  friendly_name               = "Banking Dataset"
  description                 = "Dataset for banking universal profile, applications, and artifacts"
  location                    = "US"
  default_table_expiration_ms = null
}

resource "google_bigquery_table" "user" {
  dataset_id = google_bigquery_dataset.banking.dataset_id
  table_id   = "user"

  clustering = ["user_id", "last_name"]

  schema = file("${path.module}/../bigquery/banking/table/user.json")

  deletion_protection = false
}

resource "google_bigquery_table" "application" {
  dataset_id = google_bigquery_dataset.banking.dataset_id
  table_id   = "application"

  time_partitioning {
    type  = "DAY"
    field = "started_at"
  }

  clustering = ["user_id", "application_status"]

  schema = file("${path.module}/../bigquery/banking/table/application.json")

  deletion_protection = false
}

resource "google_bigquery_table" "application_artifact" {
  dataset_id = google_bigquery_dataset.banking.dataset_id
  table_id   = "application_artifact"

  clustering = ["application_id", "status"]

  schema = templatefile("${path.module}/../bigquery/banking/table/application_artifact.json.tftpl", {
    policy_tag_id = google_data_catalog_policy_tag.sensitive_npi.id
  })

  encryption_configuration {
    kms_key_name = google_kms_crypto_key.banking_cmek_key.id
  }

  deletion_protection = false
  depends_on          = [google_kms_crypto_key_iam_member.bq_kms_binding]
}

resource "google_bigquery_table" "user_device" {
  dataset_id = google_bigquery_dataset.banking.dataset_id
  table_id   = "user_device"

  schema = file("${path.module}/../bigquery/banking/table/user_device.json")

  deletion_protection = false
}

resource "google_bigquery_table" "user_secure_message" {
  dataset_id = google_bigquery_dataset.banking.dataset_id
  table_id   = "user_secure_message"

  clustering = ["user_id", "category"]

  schema = file("${path.module}/../bigquery/banking/table/user_secure_message.json")

  deletion_protection = false
}

resource "google_bigquery_table" "retail_location" {
  dataset_id = google_bigquery_dataset.banking.dataset_id
  table_id   = "retail_location"

  clustering = ["type"]

  schema = file("${path.module}/../bigquery/banking/table/retail_location.json")

  deletion_protection = false
}

resource "google_bigquery_connection" "banking_data_postgres_connection" {
  connection_id = "banking-postgres"
  friendly_name = "banking-postgres"
  description   = "Banking Data connection with BigQuery"
  location      = "US"
  cloud_sql {
    instance_id = google_sql_database_instance.banking_data.connection_name
    database    = google_sql_database.banking.name
    type        = "POSTGRES"
    credential {
      username = google_sql_user.banking_bq_connector.name
      password = random_password.banking_bq_connector_password.result
    }
  }
}

resource "google_bigquery_connection" "banking_data_spanner_connection" {
  connection_id = "banking-spanner"
  friendly_name = "banking-spanner"
  description   = "Banking Data connection with Spanner"
  location      = "US"
  cloud_spanner {
    database = "projects/${var.project_id}/instances/${google_spanner_instance.banking_data.name}/databases/${google_spanner_database.banking.name}"
  }
}

resource "google_bigquery_connection" "iceberg" {
  connection_id = "iceberg-warehouse"
  location      = "US"
  friendly_name = "Iceberg Connection"
  cloud_resource {}

  depends_on = [google_project_service.bigqueryconnection_googleapis_com]
}

resource "google_bigquery_dataset" "iceberg_catalog" {
  dataset_id    = "iceberg_catalog"
  friendly_name = "Iceberg Catalog Dataset"
  location      = "US"

  # WARNING: This allows Terraform to delete all tables inside this dataset
  # to facilitate the location change.
  delete_contents_on_destroy = true

  depends_on = [google_project_service.bigquery_googleapis_com]
}

resource "google_bigquery_table" "account_ledger" {
  dataset_id          = google_bigquery_dataset.iceberg_catalog.dataset_id
  table_id            = "account_ledger"
  deletion_protection = false

  biglake_configuration {
    connection_id = google_bigquery_connection.iceberg.name
    storage_uri   = "${google_storage_bucket.iceberg_warehouse.url}/account_ledger/"
    file_format   = "PARQUET"
    table_format  = "ICEBERG"
  }

  schema = file("../bigquery/iceberg_catalog/table/account_ledger.json")

  depends_on = [google_storage_bucket_iam_member.iceberg_connection_access]
}

resource "google_bigquery_data_transfer_config" "scheduled_account_ledger" {
  display_name   = "account-ledger"
  location       = google_bigquery_dataset.iceberg_catalog.location
  data_source_id = "scheduled_query"
  schedule       = "every 5 minutes"

  params = {
    query = templatefile("../bigquery/iceberg_catalog/queries/copy_account_ledger.sql.tftpl", {
      project_id = var.project_id,
    })
  }

  service_account_name = google_service_account.reporting_service_account.email
}
