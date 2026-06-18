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

# Custom service account with minimal logging privileges
resource "google_service_account" "livekit_server_sa" {
  account_id   = "livekit-server-sa"
  display_name = "LiveKit Server VM Service Account"
}

# Grant logging writer role to service account
resource "google_project_iam_member" "livekit_sa_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.livekit_server_sa.email}"
}

# Grant access to LiveKit API key secret
resource "google_secret_manager_secret_iam_member" "livekit_key_accessor" {
  secret_id = google_secret_manager_secret.livekit_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.livekit_server_sa.email}"
}

# Grant access to LiveKit API secret secret
resource "google_secret_manager_secret_iam_member" "livekit_secret_accessor" {
  secret_id = google_secret_manager_secret.livekit_api_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.livekit_server_sa.email}"
}

# Reserve a static external IP address for LiveKit Media routing stability
resource "google_compute_address" "livekit_static_ip" {
  name   = "livekit-static-ip"
  region = var.region
}

# Provision GCE Instance running Container-Optimized OS
resource "google_compute_instance" "livekit_server" {
  name                      = "livekit-server-instance"
  machine_type              = "e2-medium"
  zone                      = "${var.region}-c"
  allow_stopping_for_update = true

  tags = ["livekit-server"]

  boot_disk {
    initialize_params {
      image = "projects/cos-cloud/global/images/family/cos-stable"
      size  = 20
    }
  }

  network_interface {
    network    = google_compute_network.fsi_gecx_vpc.id
    subnetwork = google_compute_subnetwork.livekit_subnet.id
    access_config {
      nat_ip = google_compute_address.livekit_static_ip.address
    }
  }

  service_account {
    email  = google_service_account.livekit_server_sa.email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  metadata = {
    startup-script = <<-EOT
      #!/bin/bash
      
      # Configure host OS iptables to allow incoming LiveKit traffic (needed for Container-Optimized OS)
      iptables -A INPUT -p tcp --dport 7880 -j ACCEPT
      iptables -A INPUT -p tcp --dport 7881 -j ACCEPT
      iptables -A INPUT -p udp --dport 50000:60000 -j ACCEPT

      mkdir -p /var/lib/livekit

      # Pull dynamic secure credentials from Secret Manager using alpine-sdk docker helper
      API_KEY=$(docker run --rm gcr.io/google.com/cloudsdktool/cloud-sdk:alpine gcloud secrets versions access latest --secret="livekit-api-key")
      API_SECRET=$(docker run --rm gcr.io/google.com/cloudsdktool/cloud-sdk:alpine gcloud secrets versions access latest --secret="livekit-api-secret")

      # Generate local configuration
      cat <<EOF > /var/lib/livekit/livekit.yaml
      port: 7880
      rtc:
        port_range_start: 50000
        port_range_end: 60000
        use_external_ip: true
      keys:
        "$${API_KEY}": "$${API_SECRET}"
      EOF

      # Start LiveKit server using host network mode for direct UDP binds
      docker rm -f livekit-server || true
      docker run -d --name=livekit-server \
        --restart=always \
        --net=host \
        --log-driver=gcplogs \
        -v /var/lib/livekit/livekit.yaml:/etc/livekit.yaml \
        livekit/livekit-server:v1.12.0 --config /etc/livekit.yaml
    EOT
  }
}
