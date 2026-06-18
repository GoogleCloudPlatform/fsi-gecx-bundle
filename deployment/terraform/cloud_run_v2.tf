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
  banking_service_url    = var.banking_service_image_url != null ? var.banking_service_image_url : "${var.region}-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/banking-service:latest"
  banking_ui_image_url   = var.banking_ui_image_url != null ? var.banking_ui_image_url : "${var.region}-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/banking-ui:latest"
  iap_login_ui_image_url = var.iap_login_ui_image_url != null ? var.iap_login_ui_image_url : "${var.region}-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/iap-login-ui:latest"
}

resource "google_cloud_run_v2_service" "banking_service" {
  count               = var.deploy_cloud_run_services ? 1 : 0
  name                = "banking-service"
  location            = var.region
  deletion_protection = false

  # To avoid TF seeing changes in Argolis environment
  scaling {
    min_instance_count = 1
    max_instance_count = 20
  }

  iap_enabled = false

  template {
    service_account = google_service_account.banking_service_account.email

    vpc_access {
      network_interfaces {
        network    = google_compute_network.fsi_gecx_vpc.name
        subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
      }
      egress = "ALL_TRAFFIC"
    }

    containers {
      image = local.banking_service_url

      resources {
        startup_cpu_boost = true
        limits = {
          cpu    = "2000m"
          memory = "1Gi"
        }
      }

      env {
        name  = "ROOT_PATH"
        value = "/api"
      }

      env {
        name  = "DATABASE_URL"
        value = "postgresql+psycopg2://${google_sql_user.banking_user.name}:${random_password.banking_password.result}@${google_sql_database_instance.banking_data.private_ip_address}/${google_sql_database.banking.name}"
      }

      env {
        name  = "DOCAI_SPLITTER_PROCESSOR_ID"
        value = google_document_ai_processor.master_splitter.id
      }
      env {
        name  = "DOCAI_W2_PROCESSOR_ID"
        value = google_document_ai_processor.w2_extractor.id
      }
      env {
        name  = "DOCAI_PAYSTUB_PROCESSOR_ID"
        value = google_document_ai_processor.paystub_extractor.id
      }
      env {
        name  = "DOCAI_BANK_STATEMENT_PROCESSOR_ID"
        value = google_document_ai_processor.bank_statement_extractor.id
      }
      env {
        name  = "DISCOVERY_ENGINE_ID"
        value = google_discovery_engine_search_engine.nova_horizon_site.engine_id
      }

      env {
        name = "LIVEKIT_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.livekit_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "LIVEKIT_API_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.livekit_api_secret.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "VOICE_AGENT_SERVICE_URL"
        value = var.deploy_cloud_run_services ? google_cloud_run_v2_service.credit_support_agent[0].uri : "http://localhost:8081"
      }

      env {
        name  = "GECX_APP_ID"
        value = var.gecx_voice_agent_id
      }

      env {
        name  = "GECX_LOCATION"
        value = var.gecx_location
      }

      dynamic "env" {
        for_each = var.set_cloud_run_audiences ? [1] : []
        content {
          name  = "IAP_AUDIENCES"
          value = local.iap_audiences
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version
    ]
  }

  depends_on = [google_project_service.run_googleapis_com]
}

data "google_compute_backend_service" "ui_backend" {
  count = var.set_cloud_run_audiences ? 1 : 0
  name  = "banking-ui-backend"
}

data "google_compute_backend_service" "service_backend" {
  count = var.set_cloud_run_audiences ? 1 : 0
  name  = "banking-service-backend"
}

# Primary URI
data "external" "banking_ui_url_primary" {
  program = ["bash", "-c", <<EOT
    URL=$(gcloud run services describe banking-ui --region=${var.region} --format='value(status.url)' 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$URL" ]; then
      echo "{\"url\": \"$URL\"}"
    else
      echo "{\"url\": \"\"}"
    fi
  EOT
  ]
}

# Secondary URI
data "external" "banking_ui_url_secondary" {
  program = ["bash", "-c", <<EOT
    URL=$(gcloud run services describe banking-ui --region=${var.region} --format=yaml 2>/dev/null | sed -n 's/.*"\(https:\/\/banking-ui-[0-9]*\.[a-z0-9-]*\.run\.app\)".*/\1/p')
    if [ $? -eq 0 ] && [ -n "$URL" ]; then
      echo "{\"url\": \"$URL\"}"
    else
      echo "{\"url\": \"\"}"
    fi
  EOT
  ]
}

locals {
  banking_ui_base_url_primary   = data.external.banking_ui_url_primary.result.url
  banking_ui_base_url_secondary = data.external.banking_ui_url_secondary.result.url
  iap_audiences                 = var.set_cloud_run_audiences ? "/projects/${data.google_project.project.number}/global/backendServices/${data.google_compute_backend_service.ui_backend[0].generated_id},/projects/${data.google_project.project.number}/global/backendServices/${data.google_compute_backend_service.service_backend[0].generated_id}" : ""
}

resource "google_cloud_run_v2_service" "banking_ui" {
  count               = var.deploy_cloud_run_services ? 1 : 0
  name                = "banking-ui"
  location            = var.region
  deletion_protection = false

  # To avoid TF seeing changes in Argolis environment
  scaling {
    min_instance_count = 1
    max_instance_count = 20
  }

  iap_enabled = false

  template {
    service_account = google_service_account.banking_service_account.email

    containers {
      image = local.banking_ui_image_url

      resources {
        startup_cpu_boost = true
      }

      env {
        name  = "VITE_BANKING_API_URL"
        value = "https://${var.custom_domain}/api"
      }
      env {
        name  = "VITE_CCAI_COMPANY_ID"
        value = var.ccai_company_id
      }
      env {
        name  = "VITE_CCAI_HOST"
        value = var.ccai_host
      }
      env {
        name  = "LIVEKIT_URL"
        value = "wss://${var.custom_domain}"
      }
      dynamic "env" {
        for_each = local.banking_ui_base_url_secondary != "" ? [1] : []
        content {
          name  = "SITEMAP_BASE_URL"
          value = local.banking_ui_base_url_secondary
        }
      }
      env {
        name  = "FIREBASE_API_KEY"
        value = data.google_firebase_web_app_config.banking_ui_app_config.api_key
      }
      env {
        name  = "FIREBASE_AUTH_DOMAIN"
        value = var.custom_domain
      }
      env {
        name  = "FIREBASE_PROJECT_ID"
        value = data.google_project.project.project_id
      }
      env {
        name  = "FIREBASE_STORAGE_BUCKET"
        value = data.google_firebase_web_app_config.banking_ui_app_config.storage_bucket
      }
      env {
        name  = "FIREBASE_MESSAGING_SENDER_ID"
        value = data.google_firebase_web_app_config.banking_ui_app_config.messaging_sender_id
      }
      env {
        name  = "FIREBASE_APP_ID"
        value = google_firebase_web_app.banking_ui_app.app_id
      }
      env {
        name  = "FIREBASE_MEASUREMENT_ID"
        value = data.google_firebase_web_app_config.banking_ui_app_config.measurement_id
      }
      dynamic "env" {
        for_each = var.cx_agent_studio_deployment_name != null ? [1] : []
        content {
          name  = "VITE_CX_AGENT_STUDIO_DEPLOYMENT_NAME"
          value = var.cx_agent_studio_deployment_name
        }
      }
      dynamic "env" {
        for_each = var.cx_agent_studio_upload_tool_name != null ? [1] : []
        content {
          name  = "VITE_CX_AGENT_STUDIO_UPLOAD_TOOL_NAME"
          value = var.cx_agent_studio_upload_tool_name
        }
      }
      dynamic "env" {
        for_each = var.cx_agent_studio_populate_content_tool_name != null ? [1] : []
        content {
          name  = "VITE_CX_AGENT_STUDIO_POPULATE_FORM_CONTENT_TOOL_NAME"
          value = var.cx_agent_studio_populate_content_tool_name
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version
    ]
  }

  depends_on = [google_project_service.run_googleapis_com]
}

resource "google_cloud_run_v2_service" "iap_login_ui" {
  count               = var.deploy_cloud_run_services && var.use_external_identities ? 1 : 0
  name                = "iap-login-ui"
  location            = var.region
  deletion_protection = false

  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  scaling {
    min_instance_count = 1
    max_instance_count = 5
  }

  template {
    service_account = google_service_account.banking_service_account.email

    containers {
      image = local.iap_login_ui_image_url

      resources {
        startup_cpu_boost = true
      }

      env {
        name  = "FIREBASE_API_KEY"
        value = data.google_firebase_web_app_config.banking_ui_app_config.api_key
      }
      env {
        name  = "FIREBASE_AUTH_DOMAIN"
        value = var.custom_domain
      }
      env {
        name  = "FIREBASE_PROJECT_ID"
        value = data.google_project.project.project_id
      }
      env {
        name  = "FIREBASE_PROJECT_NUMBER"
        value = data.google_project.project.number
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version
    ]
  }

  depends_on = [google_project_service.run_googleapis_com]
}

resource "google_service_account" "voice_agent_sa" {
  account_id   = "voice-agent-sa"
  display_name = "Cloud Run Credit Card Voice Agent Service Account"
}

# IAM permissions to access specific secrets
resource "google_secret_manager_secret_iam_member" "voice_agent_key_accessor" {
  secret_id = google_secret_manager_secret.livekit_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.voice_agent_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "voice_agent_secret_accessor" {
  secret_id = google_secret_manager_secret.livekit_api_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.voice_agent_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "banking_service_livekit_key_accessor" {
  secret_id = google_secret_manager_secret.livekit_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.banking_service_account.email}"
}

resource "google_secret_manager_secret_iam_member" "banking_service_livekit_secret_accessor" {
  secret_id = google_secret_manager_secret.livekit_api_secret.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.banking_service_account.email}"
}

# Grant Vertex AI permission to call Gemini Live
resource "google_project_iam_member" "voice_agent_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.voice_agent_sa.email}"
}

# Grant Speech Client permission to access Cloud Speech-to-Text API
resource "google_project_iam_member" "voice_agent_speech_client" {
  project = var.project_id
  role    = "roles/speech.client"
  member  = "serviceAccount:${google_service_account.voice_agent_sa.email}"
}

resource "google_cloud_run_v2_service" "credit_support_agent" {
  count               = var.deploy_cloud_run_services ? 1 : 0
  name                = "credit-support-agent"
  location            = var.region
  deletion_protection = false

  # CPU/instance scaling configurations to avoid drops
  scaling {
    min_instance_count = 1
    max_instance_count = 5
  }

  template {
    service_account = google_service_account.voice_agent_sa.email

    vpc_access {
      network_interfaces {
        network    = google_compute_network.fsi_gecx_vpc.name
        subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
      }
      egress = "ALL_TRAFFIC"
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/credit-support-agent:latest"

      resources {
        cpu_idle          = false
        startup_cpu_boost = true
        limits = {
          cpu    = "2000m" # 2 CPUs
          memory = "2Gi"   # 2GiB Memory
        }
      }

      env {
        name  = "DATABASE_URL"
        value = "postgresql+psycopg2://${google_sql_user.banking_user.name}:${random_password.banking_password.result}@${google_sql_database_instance.banking_data.private_ip_address}/${google_sql_database.banking.name}"
      }

      env {
        name  = "BANKING_SERVICE_URL"
        value = google_cloud_run_v2_service.banking_service[0].uri
      }

      env {
        name  = "LIVEKIT_URL"
        value = "ws://${google_compute_instance.livekit_server.network_interface[0].network_ip}:7880"
      }

      env {
        name = "LIVEKIT_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.livekit_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "LIVEKIT_API_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.livekit_api_secret.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "VOICE_AGENT_VIDEO_MODEL"
        value = var.voice_agent_video_model
      }

      env {
        name  = "VOICE_AGENT_AUDIO_MODEL"
        value = var.voice_agent_audio_model
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version
    ]
  }

  depends_on = [
    google_project_service.run_googleapis_com,
    google_secret_manager_secret_iam_member.voice_agent_key_accessor,
    google_secret_manager_secret_iam_member.voice_agent_secret_accessor
  ]
}

