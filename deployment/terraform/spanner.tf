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

locals {
  spanner_ddl_files = [for f in fileset("${path.module}/../spanner", "*.sql") : f if f != "seed.sql"]
}

resource "google_spanner_instance" "banking_data" {
  config       = "regional-us-central1"
  display_name = "Banking Data Spanner Instance"
  name         = "banking-data"

  # Smallest footprint: 100 processing units (0.1 node)
  processing_units = 100

  depends_on = [
    google_project_service.spanner_googleapis_com
  ]
}

resource "google_spanner_database" "banking" {
  instance            = google_spanner_instance.banking_data.name
  name                = "banking"
  deletion_protection = false
  ddl                 = [for f in local.spanner_ddl_files : file("${path.module}/../spanner/${f}")]
}

resource "terraform_data" "seed_spanner" {
  depends_on = [google_spanner_database.banking]

  input = filesha256("${path.module}/../spanner/seed.sql")

  provisioner "local-exec" {
    command = "gcloud spanner databases execute-sql ${google_spanner_database.banking.name} --instance=${google_spanner_instance.banking_data.name} --project=${var.project_id} --sql=\"$(cat ${path.module}/../spanner/seed.sql)\""
  }
}
