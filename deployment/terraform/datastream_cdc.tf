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

# Divergence A & B: Replace scheduled federated queries with real-time Google Cloud Datastream CDC
# streaming directly from PostgreSQL WAL into our BigLake Iceberg catalog for bounded domain tables.

resource "google_datastream_private_connection" "vpc_connection" {
  display_name          = "VPC Peering Connection for Datastream"
  location              = var.region
  private_connection_id = "datastream-vpc-connection"

  vpc_peering_config {
    vpc    = google_compute_network.fsi_gecx_vpc.id
    subnet = "172.16.1.0/29"
  }

  depends_on = [google_project_service.datastream_googleapis_com]
}

resource "google_datastream_connection_profile" "postgres_source" {
  display_name              = "PostgreSQL Source Profile"
  location                  = var.region
  connection_profile_id     = "postgres-source-profile"
  create_without_validation = true

  postgresql_profile {
    hostname = google_compute_address.proxy_internal_ip.address
    port     = 5432
    username = google_sql_user.banking_bq_connector.name
    password = random_password.banking_bq_connector_password.result
    database = google_sql_database.banking.name
  }

  private_connectivity {
    private_connection = google_datastream_private_connection.vpc_connection.id
  }

  depends_on = [
    google_project_service.datastream_googleapis_com,
    google_compute_instance.cloudsql_proxy_vm,
    google_compute_firewall.allow_datastream_to_proxy
  ]
}

resource "google_datastream_connection_profile" "bigquery_destination" {
  display_name          = "BigQuery Destination Profile"
  location              = var.region
  connection_profile_id = "bigquery-destination-profile"

  bigquery_profile {}

  depends_on = [google_project_service.datastream_googleapis_com]
}

resource "google_datastream_stream" "banking_cdc_stream" {
  display_name = "Banking CDC Stream to Iceberg Data Lake"
  location     = var.region
  stream_id    = "banking-cdc-stream"
  # Create the stream without auto-starting so fresh environments can finish
  # database migrations before Datastream validates publication/slot state.
  desired_state             = "NOT_STARTED"
  create_without_validation = true

  backfill_all {}

  source_config {
    source_connection_profile = google_datastream_connection_profile.postgres_source.id
    postgresql_source_config {
      publication      = "datastream_publication"
      replication_slot = "datastream_replication_slot"
      include_objects {
        postgresql_schemas {
          schema = "cards"
          postgresql_tables {
            table = "posted_transactions"
          }
          postgresql_tables {
            table = "credit_accounts"
          }
          postgresql_tables {
            table = "issued_card"
          }
          postgresql_tables {
            table = "transaction_authorization"
          }
        }
        postgresql_schemas {
          schema = "origination"
          postgresql_tables {
            table = "applications"
          }
          postgresql_tables {
            table = "credit_card_applications"
          }
          postgresql_tables {
            table = "mortgage_applications"
          }
        }
        postgresql_schemas {
          schema = "identity"
          postgresql_tables {
            table = "users"
          }
          postgresql_tables {
            table = "user_addresses"
          }
        }
        postgresql_schemas {
          schema = "kyc"
          postgresql_tables {
            table = "user_credit_profiles"
          }
        }
        postgresql_schemas {
          schema = "merchants"
          postgresql_tables {
            table = "merchant_master"
          }
          postgresql_tables {
            table = "merchant_stores"
          }
          postgresql_tables {
            table = "merchant_category_codes"
          }
        }
      }
    }
  }

  destination_config {
    destination_connection_profile = google_datastream_connection_profile.bigquery_destination.id
    bigquery_destination_config {
      single_target_dataset {
        dataset_id = google_bigquery_dataset.iceberg_catalog.id
      }
    }
  }

  lifecycle {
    ignore_changes = [
      desired_state
    ]
  }

  depends_on = [
    google_project_service.datastream_googleapis_com,
    google_bigquery_dataset.iceberg_catalog
  ]
}
