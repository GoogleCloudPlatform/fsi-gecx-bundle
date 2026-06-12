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

resource "google_compute_network" "fsi_gecx_vpc" {
  name                    = "fsi-gecx-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.servicenetworking_googleapis_com]
}

resource "google_compute_subnetwork" "fsi_gecx_subnet" {
  name                     = "fsi-gecx-subnet"
  ip_cidr_range            = "10.0.0.0/24"
  region                   = var.region
  network                  = google_compute_network.fsi_gecx_vpc.self_link
  private_ip_google_access = true
}

resource "google_compute_router" "router" {
  name    = "fsi-gecx-router"
  region  = var.region
  network = google_compute_network.fsi_gecx_vpc.self_link
}

resource "google_compute_router_nat" "nat" {
  name                               = "fsi-gecx-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
  nat_ip_allocate_option             = "AUTO_ONLY"
}

resource "google_compute_global_address" "private_service_access" {
  name          = "fsi-gecx-psa-range"
  address_type  = "INTERNAL"
  purpose       = "VPC_PEERING"
  prefix_length = 16
  network       = google_compute_network.fsi_gecx_vpc.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network = google_compute_network.fsi_gecx_vpc.id
  service = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [
    google_compute_global_address.private_service_access.name
  ]
  depends_on = [google_project_service.servicenetworking_googleapis_com]
}
