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

resource "google_project_service" "dataplex_googleapis_com" {
  service            = "dataplex.googleapis.com"
  disable_on_destroy = false
}

resource "google_dataplex_entry_group" "fraud_support_guidance" {
  project        = var.project_id
  location       = var.region
  entry_group_id = "fraud-support-guidance"
  display_name   = "Fraud Support Guidance"
  description    = "Curated Knowledge Catalog entry group for fraud voice support guidance."

  labels = {
    domain = "fraud-support"
    owner  = "banking-service"
  }

  depends_on = [google_project_service.dataplex_googleapis_com]
}

resource "google_dataplex_aspect_type" "fraud_support_policy" {
  project        = var.project_id
  location       = var.region
  aspect_type_id = "fraud-support-policy"
  display_name   = "Fraud Support Policy"
  description    = "Structured policy and workflow guidance for fraud voice support."

  metadata_template = <<EOF
{
  "name": "FraudSupportPolicy",
  "type": "record",
  "recordFields": [
    {
      "name": "topic_id",
      "type": "string",
      "index": 1,
      "constraints": { "required": true }
    },
    {
      "name": "title",
      "type": "string",
      "index": 2,
      "constraints": { "required": true }
    },
    {
      "name": "audience",
      "type": "string",
      "index": 3,
      "constraints": { "required": true }
    },
    {
      "name": "channel",
      "type": "string",
      "index": 4,
      "constraints": { "required": true }
    },
    {
      "name": "applies_when",
      "type": "array",
      "index": 5,
      "arrayItems": {
        "name": "condition",
        "type": "string"
      }
    },
    {
      "name": "must_do",
      "type": "array",
      "index": 6,
      "arrayItems": {
        "name": "instruction",
        "type": "string"
      }
    },
    {
      "name": "must_not_do",
      "type": "array",
      "index": 7,
      "arrayItems": {
        "name": "restriction",
        "type": "string"
      }
    },
    {
      "name": "tool_dependencies",
      "type": "array",
      "index": 8,
      "arrayItems": {
        "name": "tool",
        "type": "string"
      }
    },
    {
      "name": "source_policy_ref",
      "type": "string",
      "index": 9
    },
    {
      "name": "version",
      "type": "string",
      "index": 10
    },
    {
      "name": "last_reviewed",
      "type": "string",
      "index": 11
    }
  ]
}
EOF

  depends_on = [google_project_service.dataplex_googleapis_com]
}

resource "google_dataplex_aspect_type" "fraud_customer_summary" {
  project        = var.project_id
  location       = var.region
  aspect_type_id = "fraud-customer-summary"
  display_name   = "Fraud Customer Summary"
  description    = "Customer-safe summary text for fraud voice support topics."

  metadata_template = <<EOF
{
  "name": "FraudCustomerSummary",
  "type": "record",
  "recordFields": [
    {
      "name": "customer_safe_summary",
      "type": "string",
      "index": 1,
      "constraints": { "required": true }
    }
  ]
}
EOF

  depends_on = [google_project_service.dataplex_googleapis_com]
}

resource "google_dataplex_entry_type" "fraud_support_topic" {
  project       = var.project_id
  location      = var.region
  entry_type_id = "fraud-support-topic"
  display_name  = "Fraud Support Topic"
  description   = "Custom Knowledge Catalog entry type for approved fraud support guidance topics."
  type_aliases  = ["TOPIC"]
  platform      = "BANKING_SUPPORT"
  system        = "NOVA_HORIZON"

  required_aspects {
    type = google_dataplex_aspect_type.fraud_support_policy.name
  }

  depends_on = [
    google_project_service.dataplex_googleapis_com,
    google_dataplex_aspect_type.fraud_support_policy,
  ]
}

resource "google_project_iam_member" "banking_service_sa_dataplex_catalog_viewer" {
  project = data.google_project.project.project_id
  role    = "roles/dataplex.catalogViewer"
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"

  depends_on = [google_project_service.dataplex_googleapis_com]
}
