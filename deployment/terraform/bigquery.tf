# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

resource "google_bigquery_dataset" "compliance_audit" {
  dataset_id                  = "compliance_audit"
  friendly_name               = "Compliance Audit Dataset"
  description                 = "Logical audit views over catalog-native Apache Iceberg tables"
  location                    = "US"
  default_table_expiration_ms = null
}

# Views over the runtime catalog are reconciled by audit-iceberg-bootstrap
# after its REST API table creation. Managing them here would make the first
# Terraform apply fail because the externally created source tables do not yet
# exist.

resource "google_bigquery_connection" "iceberg" {
  connection_id = "iceberg-warehouse"
  location      = "US"
  friendly_name = "Lakehouse Warehouse Connection"
  cloud_resource {}

  depends_on = [google_project_service.bigqueryconnection_googleapis_com]
}

resource "google_bigquery_dataset" "oltp_cdc" {
  dataset_id    = "oltp_cdc"
  friendly_name = "OLTP Current-State CDC Replica"
  description   = "BigQuery-native merge-mode replicas of bounded AlloyDB OLTP tables, maintained by Datastream"
  location      = "US"

  # Datastream owns the mutable BigQuery-native tables in this dataset.
  # Existing environments replace the legacy, misleadingly named
  # iceberg_catalog dataset during the controlled Datastream rebuild.
  delete_contents_on_destroy = true

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_bigquery_dataset" "analytics_curated" {
  dataset_id                 = "analytics_curated"
  friendly_name              = "Curated Lakehouse Analytics"
  description                = "Business-facing analytical views over BigQuery-native OLTP current-state CDC replicas and catalog-native Iceberg audit history"
  location                   = "US"
  delete_contents_on_destroy = false
}
