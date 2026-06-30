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

# Option A: Container-Optimized OS (COS) Cloud SQL Auth Proxy bridge VM.
# Sits inside fsi-gecx-subnet, bridges traffic from Datastream's peered VPC (172.16.1.0/29)
# across the non-transitive VPC peering boundary to Cloud SQL's private IP with ZERO public IP exposure.

resource "google_service_account" "cloudsql_proxy_sa" {
  account_id   = "cloudsql-proxy-sa"
  display_name = "Cloud SQL Proxy Bridge SA for Datastream CDC"
}

resource "google_project_iam_member" "proxy_sa_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloudsql_proxy_sa.email}"
}

resource "google_compute_address" "proxy_internal_ip" {
  name         = "datastream-cloudsql-proxy-ip"
  subnetwork   = google_compute_subnetwork.fsi_gecx_subnet.id
  address_type = "INTERNAL"
  region       = var.region
}

resource "google_compute_firewall" "allow_datastream_to_proxy" {
  name    = "allow-datastream-to-cloudsql-proxy"
  network = google_compute_network.fsi_gecx_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["datastream-proxy"]
}

resource "google_compute_instance" "cloudsql_proxy_vm" {
  name         = "datastream-cloudsql-proxy"
  machine_type = "e2-small"
  zone         = var.zone
  tags         = ["datastream-proxy"]

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.fsi_gecx_subnet.id
    network_ip = google_compute_address.proxy_internal_ip.address
  }

  service_account {
    email  = google_service_account.cloudsql_proxy_sa.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = <<-EOT
      #!/bin/bash
      # Open port 5432 in Container-Optimized OS local kernel iptables firewall
      iptables -I INPUT -p tcp --dport 5432 -j ACCEPT
      # Run official Google Cloud SQL Auth Proxy container in Docker
      docker run -d --restart=always --net=host \
        gcr.io/cloud-sql-connectors/cloud-sql-proxy:latest \
        --private-ip --address=0.0.0.0 --port=5432 \
        ${google_sql_database_instance.banking_data.connection_name}
    EOT
  }

  depends_on = [
    google_project_iam_member.proxy_sa_cloudsql_client,
    google_sql_database_instance.banking_data
  ]
}
