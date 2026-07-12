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

resource "google_bigquery_dataset" "compliance_audit" {
  dataset_id                  = "compliance_audit"
  friendly_name               = "Compliance Audit Dataset"
  description                 = "Domain-segmented FSI compliance audit logs with mandatory partitioning"
  location                    = "US"
  default_table_expiration_ms = null
}

resource "google_bigquery_table" "raw_audit_outbox_cdc" {
  dataset_id          = google_bigquery_dataset.compliance_audit.dataset_id
  table_id            = "raw_audit_outbox_cdc"
  deletion_protection = false

  require_partition_filter = true
  time_partitioning {
    type  = "DAY"
    field = "created_at"
  }

  clustering = ["event_type"]
  schema     = file("${path.module}/../bigquery/compliance_audit/table/raw_audit_outbox_cdc.json")
}

resource "google_bigquery_table" "origination_audit_log" {
  dataset_id          = google_bigquery_dataset.compliance_audit.dataset_id
  table_id            = "origination_audit_log"
  deletion_protection = false

  materialized_view {
    query               = <<-SQL
      SELECT 
        event_id,
        event_type,
        JSON_VALUE(payload, '$.application_id') AS application_id,
        JSON_VALUE(payload, '$.underwriter_id') AS underwriter_id,
        payload,
        created_at
      FROM `${var.project_id}.compliance_audit.raw_audit_outbox_cdc`
      WHERE event_type IN ('APPLICATION_CREATED', 'APPLICATION_SUBMITTED', 'APPLICATION_UPDATED', 'ARTIFACT_UPLOADED', 'DOCUMENT_EXTRACTION_COMPLETED', 'UNDERWRITING_OVERRIDE_APPLIED');
    SQL
    enable_refresh      = true
    refresh_interval_ms = 1800000
  }

  depends_on = [google_bigquery_table.raw_audit_outbox_cdc]
}

resource "google_bigquery_table" "financial_ledger_audit_log" {
  dataset_id          = google_bigquery_dataset.compliance_audit.dataset_id
  table_id            = "financial_ledger_audit_log"
  deletion_protection = false

  materialized_view {
    query               = <<-SQL
      SELECT 
        event_id,
        event_type,
        JSON_VALUE(payload, '$.account_id') AS account_id,
        JSON_VALUE(payload, '$.transaction_id') AS transaction_id,
        CAST(JSON_VALUE(payload, '$.amount_cents') AS INT64) AS amount_cents,
        payload,
        created_at
      FROM `${var.project_id}.compliance_audit.raw_audit_outbox_cdc`
      WHERE event_type IN ('MONETARY_TRANSFER_EXECUTED', 'CREDIT_LIMIT_INCREASED', 'FEE_REVERSED', 'CARD_FROZEN', 'CREDIT_ACCOUNT_CREATED', 'CREDIT_CARD_ISSUED', 'CREDIT_TRANSACTION_AUTHORIZED', 'CREDIT_TRANSACTION_POSTED', 'BILL_PAYMENT_EXECUTED');
    SQL
    enable_refresh      = true
    refresh_interval_ms = 1800000
  }

  depends_on = [google_bigquery_table.raw_audit_outbox_cdc]
}

resource "google_bigquery_table" "identity_access_audit_log" {
  dataset_id          = google_bigquery_dataset.compliance_audit.dataset_id
  table_id            = "identity_access_audit_log"
  deletion_protection = false

  materialized_view {
    query               = <<-SQL
      SELECT 
        event_id,
        event_type,
        JSON_VALUE(payload, '$.user_id') AS user_id,
        payload,
        created_at
      FROM `${var.project_id}.compliance_audit.raw_audit_outbox_cdc`
      WHERE event_type IN ('USER_CREATED', 'USER_UPDATED', 'DEVICE_REGISTERED', 'MESSAGE_SENT', 'KYC_RECORD_CREATED');
    SQL
    enable_refresh      = true
    refresh_interval_ms = 1800000
  }

  depends_on = [google_bigquery_table.raw_audit_outbox_cdc]
}

resource "google_bigquery_connection" "iceberg" {
  connection_id = "iceberg-warehouse"
  location      = "US"
  friendly_name = "Lakehouse Warehouse Connection"
  cloud_resource {}

  depends_on = [google_project_service.bigqueryconnection_googleapis_com]
}

resource "google_bigquery_dataset" "iceberg_catalog" {
  dataset_id    = "iceberg_catalog"
  friendly_name = "Datastream CDC Catalog Dataset"
  location      = "US"

  # Security Finding 1.1: Do not enable delete_contents_on_destroy for production financial data lakes
  delete_contents_on_destroy = false
}

# Silver/Gold Tier: Curated Analytical Reporting Dataset & Stock Views
resource "google_bigquery_dataset" "analytics_curated" {
  dataset_id                 = "analytics_curated"
  friendly_name              = "Curated Lakehouse Analytics"
  description                = "Business-facing Silver/Gold analytical views joining raw Bronze Datastream CDC tables"
  location                   = "US"
  delete_contents_on_destroy = false
}

resource "google_bigquery_table" "system_config_audit_log" {
  dataset_id          = google_bigquery_dataset.compliance_audit.dataset_id
  table_id            = "system_config_audit_log"
  deletion_protection = false

  materialized_view {
    query               = <<-SQL
      SELECT 
        event_id,
        event_type,
        JSON_VALUE(payload, '$.product_code') AS product_code,
        payload,
        created_at
      FROM `${var.project_id}.compliance_audit.raw_audit_outbox_cdc`
      WHERE event_type IN ('CREDIT_PRODUCT_CATALOG_UPDATED', 'DEPOSIT_PRODUCT_CATALOG_UPDATED', 'SYSTEM_FEATURE_FLAG_MODIFIED');
    SQL
    enable_refresh      = true
    refresh_interval_ms = 1800000
  }

  depends_on = [google_bigquery_table.raw_audit_outbox_cdc]
}
