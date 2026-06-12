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

resource "google_discovery_engine_data_store" "gcs_site" {
  provider                    = google.google_billing
  location                    = "global"
  data_store_id               = "banking-site_1778875783412"
  display_name                = "Nova Horizon Site GCS Crawled Content"
  industry_vertical           = "GENERIC"
  content_config              = "CONTENT_REQUIRED"
  solution_types              = ["SOLUTION_TYPE_SEARCH"]
  create_advanced_site_search = false

  lifecycle {
    ignore_changes = [document_processing_config]
  }

  depends_on = [google_project_service.discoveryengine_googleapis_com]
}

resource "google_discovery_engine_search_engine" "nova_horizon_site" {
  provider       = google.google_billing
  engine_id      = "banking-site_1778875783412"
  collection_id  = "default_collection"
  location       = "global"
  display_name   = "Nova Horizon Site"
  data_store_ids = [google_discovery_engine_data_store.gcs_site.data_store_id]

  search_engine_config {
    search_tier    = "SEARCH_TIER_ENTERPRISE"
    search_add_ons = ["SEARCH_ADD_ON_LLM"]
  }

  common_config {
    company_name = "Nova Horizon Credit Union"
  }
}
