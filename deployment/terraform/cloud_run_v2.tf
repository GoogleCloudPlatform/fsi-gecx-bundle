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
  banking_service_url      = var.banking_service_image_url != null ? var.banking_service_image_url : "${var.region}-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/banking-service:latest"
  banking_ui_image_url     = var.banking_ui_image_url != null ? var.banking_ui_image_url : "${var.region}-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/banking-ui:latest"
  iap_login_ui_image_url   = var.iap_login_ui_image_url != null ? var.iap_login_ui_image_url : "${var.region}-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/iap-login-ui:latest"
  data_generator_image_url = "${var.region}-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/data-generator:latest"
  cors_allowed_origins     = join(",", distinct(concat(["https://${var.custom_domain}"], var.additional_cors_allowed_origins)))
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
    timeout                          = "${var.banking_service_timeout_seconds}s"
    service_account                  = google_service_account.banking_service_account.email
    max_instance_request_concurrency = var.banking_service_max_instance_request_concurrency

    vpc_access {
      network_interfaces {
        network    = google_compute_network.fsi_gecx_vpc.name
        subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
      }
      egress = "PRIVATE_RANGES_ONLY"
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
        value = "postgresql+psycopg2://${local.alloydb_iam_users.banking_service}@${google_alloydb_instance.banking_primary.ip_address}:5432/banking?sslmode=require"
      }

      env {
        name  = "DB_IAM_AUTH"
        value = "true"
      }

      env {
        name  = "DB_POOL_SIZE"
        value = tostring(var.banking_service_db_pool_size)
      }

      env {
        name  = "DB_MAX_OVERFLOW"
        value = tostring(var.banking_service_db_max_overflow)
      }

      env {
        name  = "DB_POOL_TIMEOUT"
        value = tostring(var.banking_service_db_pool_timeout)
      }

      env {
        name  = "PUBSUB_TOPIC_AUDIT"
        value = google_pubsub_topic.audit_events.name
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
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "true"
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
        name  = "KNOWLEDGE_CATALOG_ENABLED"
        value = "true"
      }

      env {
        name  = "KNOWLEDGE_CATALOG_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "KNOWLEDGE_CATALOG_LOCATION"
        value = var.region
      }

      env {
        name  = "KNOWLEDGE_CATALOG_ENTRY_GROUP_ID"
        value = google_dataplex_entry_group.fraud_support_guidance.entry_group_id
      }

      env {
        name  = "KNOWLEDGE_CATALOG_ENTRY_TYPE_ID"
        value = google_dataplex_entry_type.fraud_support_topic.entry_type_id
      }

      env {
        name  = "KNOWLEDGE_CATALOG_POLICY_ASPECT_TYPE_ID"
        value = google_dataplex_aspect_type.fraud_support_policy.aspect_type_id
      }

      env {
        name  = "KNOWLEDGE_CATALOG_SUMMARY_ASPECT_TYPE_ID"
        value = google_dataplex_aspect_type.fraud_customer_summary.aspect_type_id
      }

      env {
        name  = "DATA_GENERATOR_URL"
        value = var.deploy_cloud_run_services ? google_cloud_run_v2_service.data_generator[0].uri : "http://localhost:8001"
      }

      env {
        name  = "FULL_RESET_JOB_NAME"
        value = "banking-db-reset"
      }

      env {
        name  = "FULL_RESET_JOB_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "FULL_RESET_JOB_REGION"
        value = var.region
      }

      env {
        name  = "FULL_RESET_ENABLED"
        value = tostring(var.full_reset_enabled)
      }

      env {
        name  = "DATABASE_IAM_SUPPORT_USERS"
        value = join(",", local.database_iam_support_users)
      }

      dynamic "env" {
        for_each = length(local.full_reset_operator_emails) > 0 ? [1] : []
        content {
          name  = "FULL_RESET_OPERATOR_EMAILS"
          value = join(",", local.full_reset_operator_emails)
        }
      }

      env {
        name  = "CORS_ALLOWED_ORIGINS"
        value = local.cors_allowed_origins
      }

      env {
        name = "CARD_NETWORK_SWITCH_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.card_network_switch_token.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "CDC_BIGQUERY_AUTH_TABLE"
        value = "cards_transaction_authorization"
      }

      env {
        name  = "CDC_BIGQUERY_POSTED_TABLE"
        value = "cards_posted_transactions"
      }

      env {
        name  = "CDC_BIGQUERY_CURATED_DATASET"
        value = "analytics_curated"
      }

      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.banking.host
      }

      env {
        name  = "REDIS_PORT"
        value = google_redis_instance.banking.port
      }

      env {
        name = "REDIS_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.redis_password.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "GECX_APP_ID"
        value = var.cx_agent_studio_voice_agent_deployment_name
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

  depends_on = [
    google_project_service.run_googleapis_com,
    google_secret_manager_secret_iam_member.banking_service_card_network_switch_token_accessor,
    google_alloydb_user.service_iam_users,
    google_project_iam_member.banking_service_sa_alloydb_client,
    google_project_iam_member.banking_service_sa_service_usage_consumer,
  ]
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
    service_account = google_service_account.banking_ui_service_account.email

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
        name  = "VITE_DATA_GENERATOR_API_URL"
        value = "https://${var.custom_domain}/data-generator"
      }
      dynamic "env" {
        for_each = var.stable_env_url != null && var.stable_env_url != "" ? [1] : []
        content {
          name  = "VITE_STABLE_ENV_URL"
          value = var.stable_env_url
        }
      }
      dynamic "env" {
        for_each = var.feedback_url != null && var.feedback_url != "" ? [1] : []
        content {
          name  = "VITE_FEEDBACK_URL"
          value = var.feedback_url
        }
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
        name  = "VITE_ENABLE_CCAI"
        value = tostring(var.enable_ccai)
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
        for_each = var.cx_agent_studio_voice_agent_deployment_name != null ? [1] : []
        content {
          name  = "VITE_CX_AGENT_STUDIO_VOICE_AGENT_DEPLOYMENT_NAME"
          value = var.cx_agent_studio_voice_agent_deployment_name
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
      dynamic "env" {
        for_each = var.cx_agent_studio_get_user_location_tool_name != null ? [1] : []
        content {
          name  = "VITE_CX_AGENT_STUDIO_GET_USER_LOCATION_TOOL_NAME"
          value = var.cx_agent_studio_get_user_location_tool_name
        }
      }
      env {
        name  = "VITE_ENABLE_AVATAR_MODALITY"
        value = tostring(var.enable_avatar_modality)
      }
      dynamic "env" {
        for_each = var.console_viewer_group_join_url != null ? [1] : []
        content {
          name  = "VITE_CONSOLE_VIEWER_GROUP_JOIN_URL"
          value = var.console_viewer_group_join_url
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
    min_instance_count = var.voice_agent_min_instances
    max_instance_count = var.voice_agent_max_instances
  }

  template {
    service_account                  = google_service_account.voice_agent_sa.email
    max_instance_request_concurrency = var.voice_agent_max_instance_request_concurrency
    timeout                          = "${var.voice_agent_request_timeout_seconds}s"

    vpc_access {
      network_interfaces {
        network    = google_compute_network.fsi_gecx_vpc.name
        subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/credit-support-agent:latest"

      resources {
        cpu_idle          = false
        startup_cpu_boost = true
        limits = {
          cpu    = tostring(var.voice_agent_cpu)
          memory = var.voice_agent_memory
        }
      }


      env {
        name  = "DATABASE_URL"
        value = "postgresql+asyncpg://${local.alloydb_iam_users.voice_agent}@${google_alloydb_instance.banking_primary.ip_address}:5432/banking?sslmode=require"
      }

      env {
        name  = "DB_IAM_AUTH"
        value = "true"
      }

      env {
        name  = "BANKING_SERVICE_URL"
        value = "https://banking-service-${data.google_project.project.number}.${var.region}.run.app"
      }

      env {
        name  = "BANKING_SERVICE_MCP_URL"
        value = "https://banking-service-${data.google_project.project.number}.${var.region}.run.app/api/mcp/"
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

      env {
        name  = "VOICE_AGENT_MAX_CONCURRENT_SESSIONS"
        value = tostring(var.voice_agent_max_concurrent_sessions)
      }

      env {
        name  = "VOICE_AGENT_AUDIO_SESSION_CAPACITY_UNITS"
        value = tostring(var.voice_agent_audio_session_capacity_units)
      }

      env {
        name  = "VOICE_AGENT_VIDEO_SESSION_CAPACITY_UNITS"
        value = tostring(var.voice_agent_video_session_capacity_units)
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
    google_secret_manager_secret_iam_member.voice_agent_secret_accessor,
    google_alloydb_user.service_iam_users,
    google_project_iam_member.voice_agent_sa_alloydb_client,
    google_project_iam_member.voice_agent_sa_service_usage_consumer,
  ]
}

resource "google_cloud_run_v2_service" "data_generator" {
  count               = var.deploy_cloud_run_services ? 1 : 0
  name                = "data-generator"
  location            = var.region
  deletion_protection = false

  scaling {
    min_instance_count = 0
    max_instance_count = 1
  }

  template {
    service_account                  = google_service_account.data_generator_service_account.email
    max_instance_request_concurrency = var.data_generator_max_instance_request_concurrency
    timeout                          = var.data_generator_request_timeout

    vpc_access {
      network_interfaces {
        network    = google_compute_network.fsi_gecx_vpc.name
        subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = local.data_generator_image_url

      env {
        name  = "BANKING_SERVICE_URL"
        value = "https://banking-service-${data.google_project.project.number}.${var.region}.run.app"
      }

      env {
        name  = "DATA_GENERATOR_DATABASE_URL"
        value = "postgresql+psycopg2://${local.alloydb_iam_users.data_generator}@${google_alloydb_instance.banking_primary.ip_address}:5432/banking?sslmode=require"
      }

      env {
        name  = "DB_IAM_AUTH"
        value = "true"
      }

      env {
        name  = "CORS_ALLOWED_ORIGINS"
        value = local.cors_allowed_origins
      }

      env {
        name = "CARD_NETWORK_SWITCH_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.card_network_switch_token.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "SWIPE_WORKFLOW_CONCURRENCY"
        value = tostring(var.data_generator_swipe_workflow_concurrency)
      }

      env {
        name  = "PULSE_WINDOW_SECONDS"
        value = tostring(var.data_generator_pulse_window_seconds)
      }

      env {
        name  = "PULSE_MIN_EVENTS"
        value = tostring(var.data_generator_pulse_min_events)
      }

      env {
        name  = "PULSE_MAX_EVENTS"
        value = tostring(var.data_generator_pulse_max_events)
      }

      env {
        name  = "SWIPE_REQUEST_TIMEOUT_SECONDS"
        value = tostring(var.data_generator_swipe_request_timeout_seconds)
      }

      env {
        name  = "AUTO_PAYDOWN_MAX_ACCOUNTS_PER_PULSE"
        value = tostring(var.data_generator_auto_paydown_max_accounts_per_pulse)
      }

      env {
        name  = "FRAUD_PATTERN_ENABLED"
        value = tostring(var.data_generator_fraud_pattern_enabled)
      }

      env {
        name  = "FRAUD_PATTERN_RATE"
        value = tostring(var.data_generator_fraud_pattern_rate)
      }

      env {
        name  = "FRAUD_PATTERN_MAX_PER_PULSE"
        value = tostring(var.data_generator_fraud_pattern_max_per_pulse)
      }

      env {
        name  = "FRAUD_PATTERN_TARGET_MODE"
        value = var.data_generator_fraud_pattern_target_mode
      }

      env {
        name  = "DATA_GENERATOR_OPERATOR_EMAIL_DOMAINS"
        value = join(",", var.data_generator_operator_email_domains)
      }

      env {
        name  = "SCHEDULE_DISPATCH_TRANSPORT"
        value = "cloud_tasks"
      }

      env {
        name  = "CLOUD_TASKS_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "CLOUD_TASKS_LOCATION"
        value = var.region
      }

      env {
        name  = "CLOUD_TASKS_QUEUE"
        value = google_cloud_tasks_queue.data_generator_synthetic_schedule[0].name
      }

      env {
        name  = "DATA_GENERATOR_DISPATCH_URL"
        value = "https://data-generator-${data.google_project.project.number}.${var.region}.run.app"
      }

      env {
        name  = "DATA_GENERATOR_SERVICE_ACCOUNT_EMAIL"
        value = google_service_account.data_generator_service_account.email
      }

      env {
        name  = "SYNTHETIC_ALERT_FOLLOWUP_RATE"
        value = tostring(var.data_generator_synthetic_alert_followup_rate)
      }

      env {
        name  = "REDIS_HOST"
        value = google_redis_instance.banking.host
      }

      env {
        name  = "REDIS_PORT"
        value = google_redis_instance.banking.port
      }

      env {
        name = "REDIS_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.redis_password.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "PULSE_ADMISSION_REDIS_REQUIRED"
        value = "true"
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
    google_alloydb_user.service_iam_users,
    google_cloud_tasks_queue.data_generator_synthetic_schedule,
    google_service_account_iam_member.datagen_sa_cloudtasks_oidc_act_as_self,
    google_project_iam_member.datagen_sa_alloydb_client,
    google_project_iam_member.datagen_sa_service_usage_consumer,
    google_secret_manager_secret_iam_member.data_generator_card_network_switch_token_accessor,
    google_secret_manager_secret_iam_member.data_generator_redis_password_accessor,
  ]
}

# Creates the application database and cluster-wide group memberships before
# Alembic runs. The built-in administrator credential is restricted to this job.
resource "google_cloud_run_v2_job" "db_bootstrap_job" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "banking-db-bootstrap"
  location = var.region

  template {
    template {
      max_retries     = 1
      timeout         = "300s"
      service_account = google_service_account.banking_db_migration_service_account.email
      containers {
        image   = local.banking_service_url
        command = ["python"]
        args    = ["-m", "scripts.database_lifecycle", "bootstrap"]
        env {
          name  = "DATABASE_URL"
          value = "postgresql+psycopg2://postgres@${google_alloydb_instance.banking_primary.ip_address}:5432/postgres?sslmode=require"
        }
        env {
          name = "DB_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.postgres_banking_root_password.secret_id
              version = "latest"
            }
          }
        }
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "DB_MIGRATION_DATABASE_USER"
          value = local.alloydb_migration_user
        }
        env {
          name  = "CDC_REPLICATION_USER"
          value = google_alloydb_user.banking_bq_connector.user_id
        }
        env {
          name  = "IAM_DBA_USERS"
          value = join(",", [for _, v in local.db_iam_support_members : v.name])
        }
        env {
          name  = "IAM_DB_VIEWER_USERS"
          value = join(",", [for _, v in local.db_iam_viewer_members : v.name])
        }
      }
      vpc_access {
        network_interfaces {
          network    = google_compute_network.fsi_gecx_vpc.name
          subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
        }
        egress = "PRIVATE_RANGES_ONLY"
      }
    }
  }
  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
  depends_on = [
    google_secret_manager_secret_iam_member.banking_db_migration_postgres_root_password_accessor,
    google_alloydb_user.migration_iam_user,
    google_alloydb_user.banking_bq_connector,
  ]
}

# Isolated Cloud Run Job tasked with executing Alembic schema migrations.
resource "google_cloud_run_v2_job" "db_migration_job" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "banking-db-migrate"
  location = var.region

  template {
    template {
      max_retries     = 1
      timeout         = "300s"
      service_account = google_service_account.banking_db_migration_service_account.email

      containers {
        image   = "us-central1-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/banking-service:latest"
        command = ["alembic"]
        args    = ["upgrade", "head"]

        env {
          name  = "DATABASE_URL"
          value = "postgresql+psycopg2://${local.alloydb_migration_user}@${google_alloydb_instance.banking_primary.ip_address}:5432/banking?sslmode=require"
        }

        env {
          name  = "DB_IAM_AUTH"
          value = "true"
        }

        env {
          name  = "IAM_DBA_USERS"
          value = join(",", [for k, v in local.db_iam_support_members : v.name])
        }

        env {
          name  = "IAM_DB_VIEWER_USERS"
          value = join(",", [for k, v in local.db_iam_viewer_members : v.name])
        }

      }

      vpc_access {
        network_interfaces {
          network    = google_compute_network.fsi_gecx_vpc.name
          subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
        }
        egress = "PRIVATE_RANGES_ONLY"
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
    google_project_iam_member.banking_migration_sa_alloydb_client,
    google_project_iam_member.banking_migration_sa_service_usage_consumer,
    google_alloydb_user.migration_iam_user,
    google_alloydb_instance.banking_primary,
  ]
}

resource "google_cloud_run_v2_job" "db_reconcile_job" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "banking-db-reconcile"
  location = var.region
  template {
    template {
      max_retries     = 1
      timeout         = "300s"
      service_account = google_service_account.banking_db_migration_service_account.email
      containers {
        image   = local.banking_service_url
        command = ["python"]
        args    = ["-m", "scripts.database_lifecycle", "reconcile"]
        env {
          name  = "DATABASE_URL"
          value = "postgresql+psycopg2://${local.alloydb_migration_user}@${google_alloydb_instance.banking_primary.ip_address}:5432/banking?sslmode=require"
        }
        env {
          name  = "DB_IAM_AUTH"
          value = "true"
        }
        env {
          # PostgreSQL role attributes such as REPLICATION are not inherited.
          # Use the dedicated Datastream login only for slot creation while
          # keeping object ownership reconciliation on the IAM migration user.
          name  = "CDC_DATABASE_URL"
          value = "postgresql+psycopg2://${google_alloydb_user.banking_bq_connector.user_id}@${google_alloydb_instance.banking_primary.ip_address}:5432/banking?sslmode=require"
        }
        env {
          name = "CDC_DB_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.postgres_banking_bq_connector_password.secret_id
              version = "latest"
            }
          }
        }
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "DB_MIGRATION_DATABASE_USER"
          value = local.alloydb_migration_user
        }
        env {
          name  = "CDC_REPLICATION_USER"
          value = google_alloydb_user.banking_bq_connector.user_id
        }
        env {
          name  = "IAM_DBA_USERS"
          value = join(",", [for _, v in local.db_iam_support_members : v.name])
        }
        env {
          name  = "IAM_DB_VIEWER_USERS"
          value = join(",", [for _, v in local.db_iam_viewer_members : v.name])
        }
        env {
          name  = "EXPECTED_ALEMBIC_REVISION"
          value = "7c4f2a9d1e63"
        }
      }
      vpc_access {
        network_interfaces {
          network    = google_compute_network.fsi_gecx_vpc.name
          subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
        }
        egress = "PRIVATE_RANGES_ONLY"
      }
    }
  }
  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
  depends_on = [
    google_secret_manager_secret_iam_member.banking_db_migration_bq_connector_password_accessor,
    google_project_iam_member.banking_migration_sa_alloydb_client,
    google_project_iam_member.banking_migration_sa_service_usage_consumer,
    google_alloydb_user.banking_bq_connector,
  ]
}

resource "google_cloud_run_v2_job" "db_reset_job" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "banking-db-reset"
  location = var.region

  template {
    template {
      max_retries     = 0
      timeout         = "300s"
      service_account = google_service_account.banking_db_reset_service_account.email

      containers {
        image   = "us-central1-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/banking-service:latest"
        command = ["python"]
        args    = ["-m", "services.seeding_service"]

        env {
          name  = "DATABASE_URL"
          value = "postgresql+psycopg2://${local.alloydb_iam_users.banking_reset}@${google_alloydb_instance.banking_primary.ip_address}:5432/banking?sslmode=require"
        }

        env {
          name  = "DB_IAM_AUTH"
          value = "true"
        }

        env {
          name  = "PYTHONUNBUFFERED"
          value = "1"
        }

        env {
          name  = "SEED_MOCK_USER_COUNT"
          value = tostring(var.seed_mock_user_count)
        }

        env {
          name  = "DATA_GENERATOR_CLOUD_TASKS_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "DATA_GENERATOR_CLOUD_TASKS_LOCATION"
          value = var.region
        }

        env {
          name  = "DATA_GENERATOR_CLOUD_TASKS_QUEUE"
          value = google_cloud_tasks_queue.data_generator_synthetic_schedule[0].name
        }
      }

      vpc_access {
        network_interfaces {
          network    = google_compute_network.fsi_gecx_vpc.name
          subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
        }
        egress = "PRIVATE_RANGES_ONLY"
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
    google_alloydb_user.service_iam_users,
    google_cloud_tasks_queue.data_generator_synthetic_schedule,
    google_project_iam_member.banking_reset_sa_cloudtasks_queue_admin,
    google_project_iam_member.banking_reset_sa_alloydb_client,
    google_project_iam_member.banking_reset_sa_service_usage_consumer,
  ]
}

# Bounded asynchronous outbox relay. Cloud Scheduler starts one singleton job;
# a PostgreSQL advisory lock also prevents overlapping manual invocations.
resource "google_cloud_run_v2_job" "audit_outbox_relay" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "audit-outbox-relay"
  location = var.region

  template {
    parallelism = 1
    task_count  = 1
    template {
      max_retries     = 2
      timeout         = "300s"
      service_account = google_service_account.audit_outbox_relay_service_account.email
      containers {
        image   = local.banking_service_url
        command = ["python"]
        args    = ["-m", "scripts.audit_outbox_relay"]
        env {
          name  = "DATABASE_URL"
          value = "postgresql+psycopg2://${local.alloydb_iam_users.audit_relay}@${google_alloydb_instance.banking_primary.ip_address}:5432/banking?sslmode=require"
        }
        env {
          name  = "DB_IAM_AUTH"
          value = "true"
        }
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "AUDIT_EVENTS_TOPIC"
          value = google_pubsub_topic.audit_events.name
        }
        env {
          name  = "AUDIT_RELAY_BATCH_SIZE"
          value = tostring(var.audit_relay_batch_size)
        }
        env {
          name  = "AUDIT_RELAY_ENABLED"
          value = tostring(var.audit_relay_enabled)
        }
      }
      vpc_access {
        network_interfaces {
          network    = google_compute_network.fsi_gecx_vpc.name
          subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
        }
        egress = "PRIVATE_RANGES_ONLY"
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }

  depends_on = [
    google_alloydb_user.service_iam_users,
    google_project_iam_member.audit_relay_sa_alloydb_client,
    google_project_iam_member.audit_relay_sa_service_usage_consumer,
    google_pubsub_topic_iam_member.audit_relay_publisher,
  ]
}

resource "google_cloud_run_v2_job" "audit_iceberg_bootstrap" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "audit-iceberg-bootstrap"
  location = var.region

  template {
    template {
      max_retries     = 2
      timeout         = "300s"
      service_account = google_service_account.audit_iceberg_dataflow_service_account.email
      containers {
        image   = local.banking_service_url
        command = ["python"]
        args    = ["-m", "scripts.bootstrap_iceberg_catalog"]
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "AUDIT_ICEBERG_CATALOG_ID"
          value = google_biglake_iceberg_catalog.audit_lakehouse.name
        }
        env {
          name  = "AUDIT_ICEBERG_WAREHOUSE"
          value = "gs://${google_storage_bucket.iceberg_warehouse.name}/audit-lakehouse"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }

  depends_on = [
    google_storage_bucket_iam_member.audit_catalog_warehouse_object_user,
    google_project_iam_member.audit_dataflow_biglake_editor,
  ]
}

resource "google_cloud_run_v2_job" "fraud_alert_lifecycle" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "banking-fraud-alert-lifecycle"
  location = var.region

  template {
    template {
      max_retries     = 0
      timeout         = "300s"
      service_account = google_service_account.banking_service_account.email

      containers {
        image   = local.banking_service_url
        command = ["python"]
        args    = ["scripts/expire_stale_fraud_alerts.py"]

        env {
          name  = "DATABASE_URL"
          value = "postgresql+psycopg2://${local.alloydb_iam_users.banking_service}@${google_alloydb_instance.banking_primary.ip_address}:5432/banking?sslmode=require"
        }

        env {
          name  = "DB_IAM_AUTH"
          value = "true"
        }

        env {
          name  = "PYTHONUNBUFFERED"
          value = "1"
        }

        env {
          name  = "FRAUD_ALERT_NO_RESPONSE_MAX_AGE_MINUTES"
          value = tostring(var.fraud_alert_no_response_max_age_minutes)
        }

        env {
          name  = "FRAUD_ALERT_LIFECYCLE_BATCH_LIMIT"
          value = tostring(var.fraud_alert_lifecycle_batch_limit)
        }
      }

      vpc_access {
        network_interfaces {
          network    = google_compute_network.fsi_gecx_vpc.name
          subnetwork = google_compute_subnetwork.fsi_gecx_subnet.name
        }
        egress = "PRIVATE_RANGES_ONLY"
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
    google_alloydb_user.service_iam_users,
    google_project_iam_member.banking_service_sa_alloydb_client,
    google_project_iam_member.banking_service_sa_service_usage_consumer,
  ]
}

resource "google_cloud_run_v2_job" "knowledge_catalog_sync" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  name     = "banking-knowledge-catalog-sync"
  location = var.region

  template {
    template {
      max_retries     = 1
      timeout         = "300s"
      service_account = google_service_account.knowledge_catalog_sync_service_account.email

      containers {
        image   = "us-central1-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/banking-service:latest"
        command = ["python"]
        args    = ["scripts/sync_fraud_support_guidance.py"]

        env {
          name  = "KNOWLEDGE_CATALOG_ENABLED"
          value = "true"
        }

        env {
          name  = "KNOWLEDGE_CATALOG_PROJECT_ID"
          value = var.project_id
        }

        env {
          name  = "KNOWLEDGE_CATALOG_LOCATION"
          value = var.region
        }

        env {
          name  = "KNOWLEDGE_CATALOG_ENTRY_GROUP_ID"
          value = google_dataplex_entry_group.fraud_support_guidance.entry_group_id
        }

        env {
          name  = "KNOWLEDGE_CATALOG_ENTRY_TYPE_ID"
          value = google_dataplex_entry_type.fraud_support_topic.entry_type_id
        }

        env {
          name  = "KNOWLEDGE_CATALOG_POLICY_ASPECT_TYPE_ID"
          value = google_dataplex_aspect_type.fraud_support_policy.aspect_type_id
        }

        env {
          name  = "KNOWLEDGE_CATALOG_SUMMARY_ASPECT_TYPE_ID"
          value = google_dataplex_aspect_type.fraud_customer_summary.aspect_type_id
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
    google_project_iam_member.knowledge_catalog_sync_sa_catalog_editor,
    google_dataplex_entry_group.fraud_support_guidance,
    google_dataplex_entry_type.fraud_support_topic,
    google_dataplex_aspect_type.fraud_support_policy,
    google_dataplex_aspect_type.fraud_customer_summary,
  ]
}

resource "google_cloud_run_v2_job" "lakehouse_view_reconcile" {
  count               = var.deploy_cloud_run_services ? 1 : 0
  name                = "lakehouse-view-reconcile"
  location            = var.region
  deletion_protection = false

  template {
    template {
      max_retries     = 0
      timeout         = "600s"
      service_account = google_service_account.lakehouse_reconcile_service_account.email

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/fsi-gecx-bundle/lakehouse-reconcile:latest"

        env {
          name  = "PROJECT_ID"
          value = data.google_project.project.project_id
        }

        env {
          name  = "REGION"
          value = var.region
        }

        env {
          name  = "DATASTREAM_STREAM_ID"
          value = google_datastream_stream.banking_cdc_stream.stream_id
        }

        env {
          name  = "SOURCE_DATASET"
          value = google_bigquery_dataset.iceberg_catalog.dataset_id
        }

        env {
          name  = "CURATED_DATASET"
          value = google_bigquery_dataset.analytics_curated.dataset_id
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
    google_datastream_stream.banking_cdc_stream,
    google_bigquery_dataset_iam_member.lakehouse_reconcile_iceberg_data_viewer,
    google_bigquery_dataset_iam_member.lakehouse_reconcile_analytics_curated_data_editor,
    google_project_iam_member.lakehouse_reconcile_sa_bq_job_user,
    google_project_iam_member.lakehouse_reconcile_sa_datastream_admin,
  ]
}
