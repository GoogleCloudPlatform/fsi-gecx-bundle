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

# 1. Regional Key Ring & Key for Document AI (us-central1)
resource "google_kms_key_ring" "banking_keyring" {
  name       = "banking-keyring"
  location   = var.region
  depends_on = [google_project_service.kms_googleapis_com]
}

resource "google_kms_crypto_key" "docai_cmek_key" {
  name                       = "docai-cmek-key"
  key_ring                   = google_kms_key_ring.banking_keyring.id
  rotation_period            = "7776000s" # 90 days
  purpose                    = "ENCRYPT_DECRYPT"
  destroy_scheduled_duration = "2592000s" # 30 days
}

# 2. Multi-Regional Key Ring & Key for BigQuery & GCS (us)
resource "google_kms_key_ring" "banking_us_keyring" {
  name       = "banking-us-keyring"
  location   = "us"
  depends_on = [google_project_service.kms_googleapis_com]
}

resource "google_kms_crypto_key" "banking_cmek_key" {
  name                       = "banking-cmek-key"
  key_ring                   = google_kms_key_ring.banking_us_keyring.id
  rotation_period            = "7776000s" # 90 days
  purpose                    = "ENCRYPT_DECRYPT"
  destroy_scheduled_duration = "2592000s" # 30 days
}
