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

# Curated credit knowledge store behind the banking-service `search_knowledge`
# MCP tool (docs/architecture/ai-and-voice/credit_knowledge_store.md).
#
# Separate from the crawled `banking-site_*` store and the `nova_horizon_site`
# engine (discovery_engine.tf), which keep serving the website header search.
# Documents are one record per corpus section, imported from the snapshot the
# banking-service image ships (banking-service/resources/knowledge/credit/corpus)
# by the `banking-credit-knowledge-import` job (inline INCREMENTAL import, then a
# prune of ids absent from the snapshot); the schema is applied by that job.
#
# Discovery Engine IAM is project-scoped (no per-data-store policies), so both
# custom roles below apply to every data store in the project. The banking
# service SA also holds the pre-existing project-level roles/discoveryengine.viewer
# (site search), so its effective grant is wider than the searcher role.

resource "google_discovery_engine_data_store" "credit_knowledge" {
  provider                    = google.google_billing
  location                    = "global"
  data_store_id               = "credit-knowledge"
  display_name                = "Nova Horizon Credit Knowledge (curated)"
  industry_vertical           = "GENERIC"
  content_config              = "NO_CONTENT"
  solution_types              = ["SOLUTION_TYPE_SEARCH"]
  create_advanced_site_search = false

  depends_on = [google_project_service.discoveryengine_googleapis_com]
}

resource "google_project_iam_custom_role" "credit_knowledge_searcher" {
  role_id     = "custom.discoveryengine.knowledgeSearcher"
  title       = "Credit Knowledge Searcher"
  description = "Query Discovery Engine serving configs (credit knowledge search_knowledge tool)."
  permissions = ["discoveryengine.servingConfigs.search"]
}

resource "google_project_iam_custom_role" "credit_knowledge_importer" {
  role_id     = "custom.discoveryengine.knowledgeImporter"
  title       = "Credit Knowledge Importer"
  description = "Apply the corpus schema, import the credit knowledge snapshot and prune stale documents."
  permissions = [
    "discoveryengine.documents.delete",
    "discoveryengine.documents.import",
    "discoveryengine.documents.list",
    "discoveryengine.operations.get",
    "discoveryengine.schemas.get",
    "discoveryengine.schemas.update",
  ]
}

resource "google_service_account" "credit_knowledge_import_service_account" {
  account_id   = "credit-knowledge-import-sa"
  display_name = "Credit Knowledge Import Service Account"
}

resource "google_project_iam_member" "banking_service_sa_credit_knowledge_searcher" {
  project = data.google_project.project.project_id
  role    = google_project_iam_custom_role.credit_knowledge_searcher.id
  member  = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_project_iam_member" "credit_knowledge_import_sa_importer" {
  project = data.google_project.project.project_id
  role    = google_project_iam_custom_role.credit_knowledge_importer.id
  member  = "serviceAccount:${google_service_account.credit_knowledge_import_service_account.email}"
}

resource "google_cloud_run_v2_job" "credit_knowledge_import" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "banking-credit-knowledge-import"
  location = var.region

  template {
    template {
      max_retries     = 1
      timeout         = "1200s"
      service_account = google_service_account.credit_knowledge_import_service_account.email

      containers {
        image   = "us-central1-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/banking-service:latest"
        command = ["python"]
        args    = ["scripts/import_credit_knowledge.py"]

        env {
          name  = "CREDIT_KNOWLEDGE_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "CREDIT_KNOWLEDGE_LOCATION"
          value = google_discovery_engine_data_store.credit_knowledge.location
        }

        env {
          name  = "CREDIT_KNOWLEDGE_DATA_STORE_ID"
          value = google_discovery_engine_data_store.credit_knowledge.data_store_id
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version
    ]
  }

  depends_on = [
    google_project_service.run_googleapis_com,
    google_project_iam_member.credit_knowledge_import_sa_importer,
    google_discovery_engine_data_store.credit_knowledge,
  ]
}
