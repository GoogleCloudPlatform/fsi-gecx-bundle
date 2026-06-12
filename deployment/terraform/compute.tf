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

resource "google_compute_instance" "jump-instance" {
  boot_disk {
    auto_delete = true
    device_name = "fsi-gecx-vpc-jump-instance-boot-disk"

    initialize_params {
      image = "projects/debian-cloud/global/images/debian-12-bookworm-v20260528"
      size  = 10
      type  = "pd-balanced"
    }

    mode = "READ_WRITE"
  }

  can_ip_forward      = false
  deletion_protection = false
  enable_display      = false

  labels = {
    goog-ec-src           = "vm_add-tf"
    goog-ops-agent-policy = "v2-template-1-7-0"
  }

  machine_type = "e2-micro"

  metadata = {
    enable-osconfig = "TRUE"
  }

  name = "fsi-gecx-vpc-jump-instance"

  network_interface {
    queue_count = 0
    stack_type  = "IPV4_ONLY"
    subnetwork  = google_compute_subnetwork.fsi_gecx_subnet.id
  }

  reservation_affinity {
    type = "ANY_RESERVATION"
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
    provisioning_model  = "STANDARD"
  }

  service_account {
    email  = google_service_account.jump_instance_service_account.email
    scopes = ["https://www.googleapis.com/auth/devstorage.read_only", "https://www.googleapis.com/auth/logging.write", "https://www.googleapis.com/auth/monitoring.write", "https://www.googleapis.com/auth/service.management.readonly", "https://www.googleapis.com/auth/servicecontrol", "https://www.googleapis.com/auth/trace.append"]
  }

  shielded_instance_config {
    enable_integrity_monitoring = true
    enable_secure_boot          = false
    enable_vtpm                 = true
  }

  zone = "us-central1-a"
}

module "ops_agent_policy" {
  source        = "github.com/terraform-google-modules/terraform-google-cloud-operations/modules/ops-agent-policy"
  zone          = "us-central1-a"
  assignment_id = "goog-ops-agent-v2-template-1-7-0-us-central1-a"
  agents_rule = {
    package_state = "installed"
    version       = "latest"
  }
  instance_filter = {
    all = false
    inclusion_labels = [{
      labels = {
        goog-ops-agent-policy = "v2-template-1-7-0"
      }
    }]
  }
  depends_on = [google_project_service.osconfig_googleapis_com]
}
