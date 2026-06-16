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

resource "google_bigquery_connection" "banking_data_store_connection" {
  connection_id = "banking-data-connection"
  friendly_name = "banking-data-connection"
  description   = "Banking Data connection with BigQuery"
  location      = "US"
  cloud_sql {
    instance_id = google_sql_database_instance.banking_data.connection_name
    database    = google_sql_database.banking.name
    type        = "POSTGRES"
    credential {
      username = google_sql_user.banking_user.name
      password = random_password.banking_password.result
    }
  }
}
