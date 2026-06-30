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

  # Security Finding 1.1: Do not enable delete_contents_on_destroy for production financial data lakes
  delete_contents_on_destroy = false
}

resource "google_bigquery_table" "posted_transactions" {
  dataset_id = google_bigquery_dataset.iceberg_catalog.dataset_id
  table_id   = "posted_transactions"
  # Security Finding 1.1: Enable deletion_protection in production environments
  deletion_protection = false

  biglake_configuration {
    connection_id = google_bigquery_connection.iceberg.name
    storage_uri   = "${google_storage_bucket.iceberg_warehouse.url}/posted_transactions/"
    file_format   = "PARQUET"
    table_format  = "ICEBERG"
  }

  schema = file("${path.module}/../bigquery/iceberg_catalog/table/posted_transactions.json")

  depends_on = [google_storage_bucket_iam_member.iceberg_connection_access]
}

resource "google_bigquery_table" "applications_lake" {
  dataset_id          = google_bigquery_dataset.iceberg_catalog.dataset_id
  table_id            = "applications"
  deletion_protection = false

  biglake_configuration {
    connection_id = google_bigquery_connection.iceberg.name
    storage_uri   = "${google_storage_bucket.iceberg_warehouse.url}/applications/"
    file_format   = "PARQUET"
    table_format  = "ICEBERG"
  }

  schema = file("${path.module}/../bigquery/iceberg_catalog/table/applications.json")

  depends_on = [google_storage_bucket_iam_member.iceberg_connection_access]
}

resource "google_bigquery_table" "users_lake" {
  dataset_id          = google_bigquery_dataset.iceberg_catalog.dataset_id
  table_id            = "users"
  deletion_protection = false

  biglake_configuration {
    connection_id = google_bigquery_connection.iceberg.name
    storage_uri   = "${google_storage_bucket.iceberg_warehouse.url}/users/"
    file_format   = "PARQUET"
    table_format  = "ICEBERG"
  }

  schema = file("${path.module}/../bigquery/iceberg_catalog/table/users.json")

  depends_on = [google_storage_bucket_iam_member.iceberg_connection_access]
}

resource "google_bigquery_table" "issued_card" {
  dataset_id          = google_bigquery_dataset.iceberg_catalog.dataset_id
  table_id            = "issued_card"
  deletion_protection = false

  biglake_configuration {
    connection_id = google_bigquery_connection.iceberg.name
    storage_uri   = "${google_storage_bucket.iceberg_warehouse.url}/issued_card/"
    file_format   = "PARQUET"
    table_format  = "ICEBERG"
  }

  schema = file("${path.module}/../bigquery/iceberg_catalog/table/issued_card.json")

  depends_on = [google_storage_bucket_iam_member.iceberg_connection_access]
}

resource "google_bigquery_table" "transaction_authorization" {
  dataset_id          = google_bigquery_dataset.iceberg_catalog.dataset_id
  table_id            = "transaction_authorization"
  deletion_protection = false

  biglake_configuration {
    connection_id = google_bigquery_connection.iceberg.name
    storage_uri   = "${google_storage_bucket.iceberg_warehouse.url}/transaction_authorization/"
    file_format   = "PARQUET"
    table_format  = "ICEBERG"
  }

  schema = file("${path.module}/../bigquery/iceberg_catalog/table/transaction_authorization.json")

  depends_on = [google_storage_bucket_iam_member.iceberg_connection_access]
}

resource "google_bigquery_table" "credit_card_applications" {
  dataset_id          = google_bigquery_dataset.iceberg_catalog.dataset_id
  table_id            = "credit_card_applications"
  deletion_protection = false

  biglake_configuration {
    connection_id = google_bigquery_connection.iceberg.name
    storage_uri   = "${google_storage_bucket.iceberg_warehouse.url}/credit_card_applications/"
    file_format   = "PARQUET"
    table_format  = "ICEBERG"
  }

  schema = file("${path.module}/../bigquery/iceberg_catalog/table/credit_card_applications.json")

  depends_on = [google_storage_bucket_iam_member.iceberg_connection_access]
}

resource "google_bigquery_table" "mortgage_applications" {
  dataset_id          = google_bigquery_dataset.iceberg_catalog.dataset_id
  table_id            = "mortgage_applications"
  deletion_protection = false

  biglake_configuration {
    connection_id = google_bigquery_connection.iceberg.name
    storage_uri   = "${google_storage_bucket.iceberg_warehouse.url}/mortgage_applications/"
    file_format   = "PARQUET"
    table_format  = "ICEBERG"
  }

  schema = file("${path.module}/../bigquery/iceberg_catalog/table/mortgage_applications.json")

  depends_on = [google_storage_bucket_iam_member.iceberg_connection_access]
}

# Silver/Gold Tier: Curated Analytical Reporting Dataset & Stock Views
resource "google_bigquery_dataset" "analytics_curated" {
  dataset_id                 = "analytics_curated"
  friendly_name              = "Curated Lakehouse Analytics"
  description                = "Business-facing Silver/Gold analytical views joining raw Bronze Datastream CDC Iceberg tables"
  location                   = "US"
  delete_contents_on_destroy = false
}

resource "google_bigquery_table" "enriched_posted_transactions_view" {
  dataset_id          = google_bigquery_dataset.analytics_curated.dataset_id
  table_id            = "enriched_posted_transactions"
  deletion_protection = false

  view {
    query          = <<-SQL
      SELECT 
        pt.id AS transaction_id,
        pt.account_id,
        c.id AS card_id,
        c.last_four AS card_last_four,
        c.is_active AS card_is_active,
        pt.amount_cents,
        auth.merchant_name,
        pt.description,
        pt.posted_at,
        auth.status AS authorization_status,
        auth.decline_reason
      FROM `${var.project_id}.iceberg_catalog.posted_transactions` pt
      LEFT JOIN `${var.project_id}.iceberg_catalog.transaction_authorization` auth ON pt.authorization_id = auth.id
      LEFT JOIN `${var.project_id}.iceberg_catalog.issued_card` c ON auth.card_id = c.id;
    SQL
    use_legacy_sql = false
  }

  depends_on = [
    google_bigquery_table.posted_transactions,
    google_bigquery_table.transaction_authorization,
    google_bigquery_table.issued_card
  ]
}

resource "google_bigquery_table" "unified_applications_view" {
  dataset_id          = google_bigquery_dataset.analytics_curated.dataset_id
  table_id            = "unified_applications"
  deletion_protection = false

  view {
    query          = <<-SQL
      SELECT 
        app.application_id,
        app.user_id,
        u.email AS applicant_email,
        app.status,
        app.product_category AS application_type,
        cc.card_product_id,
        cc.requested_limit_cents AS credit_card_requested_limit_cents,
        m.requested_loan_cents AS mortgage_requested_loan_cents,
        m.property_address AS mortgage_property_address,
        m.estimated_value_cents AS mortgage_estimated_value_cents,
        app.started_at
      FROM `${var.project_id}.iceberg_catalog.applications` app
      LEFT JOIN `${var.project_id}.iceberg_catalog.users` u ON app.user_id = u.id
      LEFT JOIN `${var.project_id}.iceberg_catalog.credit_card_applications` cc ON app.id = cc.application_id
      LEFT JOIN `${var.project_id}.iceberg_catalog.mortgage_applications` m ON app.id = m.application_id;
    SQL
    use_legacy_sql = false
  }

  depends_on = [
    google_bigquery_table.applications_lake,
    google_bigquery_table.users_lake,
    google_bigquery_table.credit_card_applications,
    google_bigquery_table.mortgage_applications
  ]
}
