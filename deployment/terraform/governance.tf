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

resource "google_data_catalog_taxonomy" "banking_privacy_taxonomy" {
  project                = var.project_id
  display_name           = "Banking Privacy Taxonomy V3 - ${var.project_id}"
  description            = "Taxonomy for securing financial PII and NPI"
  region                 = "us"
  activated_policy_types = ["FINE_GRAINED_ACCESS_CONTROL"]

  lifecycle { prevent_destroy = true }

  depends_on = [google_project_service.datacatalog_googleapis_com]
}

resource "google_data_catalog_policy_tag" "sensitive_npi" {
  taxonomy     = google_data_catalog_taxonomy.banking_privacy_taxonomy.id
  display_name = "Sensitive Financial NPI"
  description  = "Policy tag applied to extraction payloads containing income, SSNs, and tax data"

  lifecycle { prevent_destroy = true }
}

resource "google_bigquery_datapolicy_data_policy" "masking_policy" {
  project          = var.project_id
  location         = "us"
  data_policy_id   = "mask_sensitive_npi"
  policy_tag       = google_data_catalog_policy_tag.sensitive_npi.name
  data_policy_type = "DATA_MASKING_POLICY"
  data_masking_policy {
    predefined_expression = "DEFAULT_MASKING_VALUE"
  }

  lifecycle { prevent_destroy = true }
}

# Grant Fine-Grained Reader to Banking Service SA to query policy-tagged BQ columns
resource "google_data_catalog_policy_tag_iam_member" "banking_service_fine_grained_reader" {
  policy_tag = google_data_catalog_policy_tag.sensitive_npi.id
  role       = "roles/datacatalog.categoryFineGrainedReader"
  member     = "serviceAccount:banking-service-sa@${var.project_id}.iam.gserviceaccount.com"
}

# Grant Fine-Grained Reader to local developers to query policy-tagged BQ columns
resource "google_data_catalog_policy_tag_iam_member" "local_developer_fine_grained_reader" {
  policy_tag = google_data_catalog_policy_tag.sensitive_npi.id
  role       = "roles/datacatalog.categoryFineGrainedReader"
  member     = "user:erikvoit@gcp.solutions"
}
