# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

locals {
  alloydb_iam_users = {
    banking_reset   = replace(google_service_account.banking_db_reset_service_account.email, ".gserviceaccount.com", "")
    banking_service = replace(google_service_account.banking_service_account.email, ".gserviceaccount.com", "")
    voice_agent     = replace(google_service_account.voice_agent_sa.email, ".gserviceaccount.com", "")
    data_generator  = replace(google_service_account.data_generator_service_account.email, ".gserviceaccount.com", "")
    ledger_service  = replace(google_service_account.ledger_service_account.email, ".gserviceaccount.com", "")
    kyc_service     = replace(google_service_account.kyc_service_account.email, ".gserviceaccount.com", "")
  }
  alloydb_migration_user = replace(google_service_account.banking_db_migration_service_account.email, ".gserviceaccount.com", "")

  db_iam_support_members = {
    for member in distinct(concat(local.database_iam_support_users, local.developer_iam_members)) :
    member => {
      name = split(":", member)[0] == "serviceAccount" ? replace(split(":", member)[1], ".gserviceaccount.com", "") : split(":", member)[1]
    }
  }
  db_iam_viewer_members = {
    for member in local.iam_console_viewers :
    member => {
      name = split(":", member)[0] == "serviceAccount" ? replace(split(":", member)[1], ".gserviceaccount.com", "") : split(":", member)[1]
    }
  }
  # google_alloydb_user in google provider 7.28 cannot model IAM_GROUP even
  # though the AlloyDB API supports it. The release controller reconciles these
  # groups with gcloud; Terraform continues to own their project IAM bindings.
  db_iam_support_users = {
    for member, principal in local.db_iam_support_members : member => principal
    if split(":", member)[0] != "group"
  }
  db_iam_viewer_users = {
    for member, principal in local.db_iam_viewer_members : member => principal
    if split(":", member)[0] != "group"
  }
}

resource "random_password" "postgres_root_password" {
  length  = 16
  special = false
}

resource "random_password" "banking_bq_connector_password" {
  length  = 16
  special = false
}

resource "google_alloydb_cluster" "banking_data" {
  cluster_id          = "banking-data"
  location            = var.region
  database_version    = "POSTGRES_18"
  deletion_protection = var.alloydb_deletion_protection

  network_config {
    network            = google_compute_network.fsi_gecx_vpc.id
    allocated_ip_range = google_compute_global_address.private_service_access.name
  }

  initial_user {
    user     = "postgres"
    password = random_password.postgres_root_password.result
  }

  automated_backup_policy {
    enabled = true
    weekly_schedule {
      days_of_week = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
      start_times {
        hours   = 2
        minutes = 0
      }
    }
    quantity_based_retention {
      count = 7
    }
  }

  continuous_backup_config {
    enabled              = true
    recovery_window_days = 7
  }

  dataplex_config {
    enabled = true
  }

  depends_on = [
    google_project_service.alloydb_googleapis_com,
    google_service_networking_connection.private_vpc_connection,
  ]
}

resource "google_alloydb_instance" "banking_primary" {
  cluster           = google_alloydb_cluster.banking_data.name
  instance_id       = "banking-primary"
  instance_type     = "PRIMARY"
  availability_type = var.alloydb_availability_type

  machine_config {
    cpu_count = var.alloydb_cpu_count
  }

  database_flags = {
    "alloydb.iam_authentication" = "on"
    "alloydb.logical_decoding"   = "on"
  }

  query_insights_config {
    query_string_length     = 1024
    query_plans_per_minute  = 5
    record_application_tags = true
    record_client_address   = true
  }
}

resource "google_alloydb_user" "banking_bq_connector" {
  cluster             = google_alloydb_cluster.banking_data.name
  user_id             = "banking_bq_connector"
  user_type           = "ALLOYDB_BUILT_IN"
  password_wo         = random_password.banking_bq_connector_password.result
  password_wo_version = 1
  database_roles      = ["alloydbsuperuser"]
  depends_on          = [google_alloydb_instance.banking_primary]
}

resource "google_alloydb_user" "service_iam_users" {
  for_each       = local.alloydb_iam_users
  cluster        = google_alloydb_cluster.banking_data.name
  user_id        = each.value
  user_type      = "ALLOYDB_IAM_USER"
  database_roles = ["alloydbiamuser"]
  depends_on     = [google_alloydb_instance.banking_primary]
}

resource "google_alloydb_user" "migration_iam_user" {
  cluster        = google_alloydb_cluster.banking_data.name
  user_id        = local.alloydb_migration_user
  user_type      = "ALLOYDB_IAM_USER"
  database_roles = ["alloydbiamuser", "alloydbsuperuser"]
  depends_on     = [google_alloydb_instance.banking_primary]
}

resource "google_alloydb_user" "database_iam_support_users" {
  for_each       = local.db_iam_support_users
  cluster        = google_alloydb_cluster.banking_data.name
  user_id        = each.value.name
  user_type      = "ALLOYDB_IAM_USER"
  database_roles = ["alloydbiamuser"]
  depends_on     = [google_alloydb_instance.banking_primary]
}

resource "google_alloydb_user" "database_iam_viewer_users" {
  for_each       = local.db_iam_viewer_users
  cluster        = google_alloydb_cluster.banking_data.name
  user_id        = each.value.name
  user_type      = "ALLOYDB_IAM_USER"
  database_roles = ["alloydbiamuser"]
  depends_on     = [google_alloydb_instance.banking_primary]
}
