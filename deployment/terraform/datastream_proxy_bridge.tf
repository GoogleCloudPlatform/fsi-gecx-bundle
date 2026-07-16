# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

# Datastream private connectivity is VPC peering and can't transit AlloyDB's
# Private Service Access peering. This TCP bridge gives Datastream a routable
# endpoint while AlloyDB remains private-IP only.

resource "google_compute_address" "datastream_alloydb_proxy_internal_ip" {
  name         = "datastream-alloydb-proxy-ip"
  subnetwork   = google_compute_subnetwork.fsi_gecx_subnet.id
  address_type = "INTERNAL"
  region       = var.region
}

resource "google_compute_firewall" "allow_datastream_to_alloydb_proxy" {
  name    = "allow-datastream-to-alloydb-proxy"
  network = google_compute_network.fsi_gecx_vpc.name
  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }
  source_ranges = ["172.16.1.0/29"]
  target_tags   = ["datastream-alloydb-proxy"]
}

resource "google_compute_instance" "datastream_alloydb_proxy" {
  name         = "datastream-alloydb-proxy"
  machine_type = "e2-small"
  zone         = var.zone
  tags         = ["datastream-alloydb-proxy"]
  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
    }
  }
  network_interface {
    subnetwork = google_compute_subnetwork.fsi_gecx_subnet.id
    network_ip = google_compute_address.datastream_alloydb_proxy_internal_ip.address
  }
  metadata = {
    startup-script = <<-EOT
      #!/bin/bash
      set -euo pipefail
      iptables -C INPUT -p tcp --dport 5432 -s 172.16.1.0/29 -j ACCEPT 2>/dev/null || \
        iptables -I INPUT -p tcp --dport 5432 -s 172.16.1.0/29 -j ACCEPT
      cat >/etc/systemd/system/datastream-alloydb-proxy.service <<'UNIT'
      [Unit]
      Description=Datastream to AlloyDB TCP bridge
      After=docker.service network-online.target
      Requires=docker.service

      [Service]
      ExecStartPre=-/usr/bin/docker rm -f datastream-alloydb-proxy
      ExecStartPre=/usr/bin/docker pull alpine/socat@sha256:beb4a68d9e4fe6b0f21ea774a0fde6c31f580dde6368939ed70100c5385b015e
      ExecStart=/usr/bin/docker run --rm --name datastream-alloydb-proxy --net=host alpine/socat@sha256:beb4a68d9e4fe6b0f21ea774a0fde6c31f580dde6368939ed70100c5385b015e TCP-LISTEN:5432,fork,reuseaddr TCP:${google_alloydb_instance.banking_primary.ip_address}:5432
      Restart=always
      RestartSec=10

      [Install]
      WantedBy=multi-user.target
      UNIT
      systemctl daemon-reload
      systemctl enable --now datastream-alloydb-proxy.service
    EOT
  }
  depends_on = [
    google_alloydb_instance.banking_primary,
    google_compute_router_nat.nat,
  ]
}
