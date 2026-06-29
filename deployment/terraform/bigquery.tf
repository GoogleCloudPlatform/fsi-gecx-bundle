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

resource "google_bigquery_connection" "banking_data_postgres_connection" {
  connection_id = "banking-postgres-connection"
  friendly_name = "banking-postgres-connection"
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
  connection_id = "banking-spanner-connection"
  friendly_name = "banking-spanner-connection"
  description   = "Banking Data connection with Spanner"
  location      = "US"
  cloud_spanner {
    database = "projects/${var.project_id}/instances/${google_spanner_instance.banking_data.name}/databases/${google_spanner_database.banking.name}"
  }
}

resource "google_bigquery_dataset" "compliance_audit" {
  dataset_id                  = "compliance_audit"
  friendly_name               = "Compliance Audit Dataset"
  description                 = "Domain-segmented FSI compliance audit logs with mandatory partitioning"
  location                    = "US"
  default_table_expiration_ms = null
}

resource "google_bigquery_table" "origination_audit_log" {
  dataset_id          = google_bigquery_dataset.compliance_audit.dataset_id
  table_id            = "origination_audit_log"
  deletion_protection = false

  require_partition_filter = true
  time_partitioning {
    type  = "DAY"
    field = "created_at"
  }

  clustering = ["application_id", "event_type"]
  schema     = file("${path.module}/../bigquery/compliance_audit/table/origination_audit_log.json")
}

resource "google_bigquery_table" "financial_ledger_audit_log" {
  dataset_id          = google_bigquery_dataset.compliance_audit.dataset_id
  table_id            = "financial_ledger_audit_log"
  deletion_protection = false

  require_partition_filter = true
  time_partitioning {
    type  = "MONTH"
    field = "created_at"
  }

  clustering = ["account_id", "event_type"]
  schema     = file("${path.module}/../bigquery/compliance_audit/table/financial_ledger_audit_log.json")
}

resource "google_bigquery_table" "identity_access_audit_log" {
  dataset_id          = google_bigquery_dataset.compliance_audit.dataset_id
  table_id            = "identity_access_audit_log"
  deletion_protection = false

  require_partition_filter = true
  time_partitioning {
    type  = "DAY"
    field = "created_at"
  }

  clustering = ["user_id", "event_type"]
  schema     = file("${path.module}/../bigquery/compliance_audit/table/identity_access_audit_log.json")
}
