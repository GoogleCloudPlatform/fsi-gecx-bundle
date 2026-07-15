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

variable "docai_location" {
  type        = string
  description = "The location for Document AI processors (e.g. 'us' or 'eu')"
  default     = "us"
}

variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-c"
}

variable "deploy_cloud_build_triggers" {
  type    = bool
  default = false
}

variable "deploy_cloud_run_services" {
  type    = bool
  default = false
}

variable "banking_service_image_url" {
  type    = string
  default = null
}

variable "banking_ui_image_url" {
  type    = string
  default = null
}

variable "iap_login_ui_image_url" {
  type    = string
  default = null
}

variable "enable_ccai" {
  type    = bool
  default = false
}

variable "ccai_company_id" {
  type    = string
  default = null
}

variable "ccai_host" {
  type    = string
  default = null
}

variable "custom_domain" {
  description = "The custom domain for the Load Balancer."
  type        = string
}

variable "set_cloud_run_audiences" {
  description = "Whether to set the Cloud Run audiences env variable."
  type        = bool
  default     = false
}

variable "github_app_installation_id" {
  type    = string
  default = null

  validation {
    condition     = var.deploy_cloud_build_triggers && var.manage_github_connection ? (var.github_app_installation_id != null && var.github_app_installation_id != "") : true
    error_message = "github_app_installation_id must be provided when deploy_cloud_build_triggers is true."
  }
}

variable "github_repo_remote_uri" {
  type    = string
  default = "https://github.com/GoogleCloudPlatform/fsi-gecx-bundle.git"

  validation {
    condition     = var.deploy_cloud_build_triggers ? (var.github_repo_remote_uri != null && var.github_repo_remote_uri != "") : true
    error_message = "github_repo_remote_uri must be provided when deploy_cloud_build_triggers is true."
  }
}

variable "github_connection_name" {
  type    = string
  default = "GoogleCloudPlatform"
}

variable "github_oauth_token_secret_name" {
  type = string

  validation {
    condition     = var.deploy_cloud_build_triggers ? (var.github_oauth_token_secret_name != null && var.github_oauth_token_secret_name != "") : true
    error_message = "github_oauth_token_secret_name must be provided when deploy_cloud_build_triggers is true."
  }
}

variable "manage_github_connection" {
  type    = bool
  default = false
}

variable "cx_agent_studio_deployment_name" {
  type    = string
  default = null
}

variable "cx_agent_studio_upload_tool_name" {
  type    = string
  default = null
}

variable "cx_agent_studio_populate_content_tool_name" {
  type    = string
  default = null
}

variable "cx_agent_studio_get_user_location_tool_name" {
  type    = string
  default = null
}

variable "governance_project_id" {
  type        = string
  description = "Project ID for centralized Data Catalog Taxonomies and Policy Tags. If omitted, defaults to var.project_id."
  default     = null
}

variable "use_external_identities" {
  type        = bool
  default     = false
  description = "Whether to enable the blocking functions in the agent. This cannot be enabled in Argolis as they require unauthenticated invocations as per https://www.npmjs.com/package/gcip-cloud-functions."
}

variable "enable_blocking_functions" {
  type        = bool
  default     = false
  description = "Whether to enable the blocking functions in the agent."
}

variable "repo_branch_expression" {
  type        = string
  description = "The target branch filter for Cloud Build triggers (e.g., ^main$ or ^feature/.*$)"
  default     = "^main$"
}

variable "repo_tag_expression" {
  type        = string
  description = "The target tag filter for Cloud Build triggers (e.g., ^v.*$)"
  default     = "^(\\d+)\\.(\\d+)\\.(\\d+)$"
}

variable "cloud_build_trigger_event" {
  type        = string
  description = "The event type to trigger Cloud Build runs. Allowed values: push_to_branch, push_to_tag"
  default     = "push_to_branch"

  validation {
    condition     = contains(["push_to_branch", "push_to_tag"], var.cloud_build_trigger_event)
    error_message = "The cloud_build_trigger_event variable must be either 'push_to_branch' or 'push_to_tag'."
  }
}

resource "terraform_data" "validate_blocking_functions" {
  lifecycle {
    precondition {
      condition     = !var.enable_blocking_functions || var.use_external_identities
      error_message = "enable_blocking_functions can only be set to true if use_external_identities is set to true."
    }
  }
}

resource "terraform_data" "validate_ccai" {
  lifecycle {
    precondition {
      condition     = !var.enable_ccai || (var.ccai_company_id != null && var.ccai_company_id != "" && var.ccai_host != null && var.ccai_host != "")
      error_message = "ccai_company_id and ccai_host must be provided when enable_ccai is true."
    }
  }
}

variable "gecx_agent_folder" {
  type    = string
  default = "Nova_Horizon_Bot_v2"
}

variable "voice_agent_video_model" {
  type        = string
  description = "The Gemini Live model to use for video mode"
}

variable "voice_agent_audio_model" {
  type        = string
  description = "The Gemini Live model to use for audio mode"
}

variable "cx_agent_studio_voice_agent_deployment_name" {
  type        = string
  description = "The target CX Agent Studio Application Deployment resource name for voice consultation"
  default     = null
}

variable "gecx_location" {
  type        = string
  description = "The location for GECX API endpoints (e.g. 'us' or 'eu')"
  default     = "us"
}

variable "banking_service_db_pool_size" {
  type        = number
  description = "Steady-state SQLAlchemy pool size per banking-service instance."
  default     = 24
}

variable "banking_service_db_max_overflow" {
  type        = number
  description = "Additional SQLAlchemy overflow connections allowed per banking-service instance."
  default     = 16
}

variable "banking_service_db_pool_timeout" {
  type        = number
  description = "Seconds to wait for a DB connection before failing fast."
  default     = 5
}

variable "banking_service_max_instance_request_concurrency" {
  type        = number
  description = "Maximum concurrent requests per banking-service Cloud Run instance."
  default     = 16
}

variable "voice_agent_max_instance_request_concurrency" {
  type        = number
  description = "Maximum simultaneous HTTP control requests per credit-support-agent instance."
  default     = 8

  validation {
    condition     = var.voice_agent_max_instance_request_concurrency >= 1
    error_message = "voice_agent_max_instance_request_concurrency must be at least 1."
  }
}

variable "voice_agent_cpu" {
  type        = number
  description = "vCPU allocated to each credit-support-agent Cloud Run instance. Qualify changes with separate audio and avatar probes."
  default     = 4

  validation {
    condition     = contains([1, 2, 4, 6, 8], var.voice_agent_cpu)
    error_message = "voice_agent_cpu must be one of 1, 2, 4, 6, or 8."
  }
}

variable "voice_agent_memory" {
  type        = string
  description = "Memory allocated to each credit-support-agent Cloud Run instance."
  default     = "4Gi"

  validation {
    condition     = can(regex("^[1-9][0-9]*(Mi|Gi)$", var.voice_agent_memory))
    error_message = "voice_agent_memory must be a positive Mi or Gi quantity, for example 4Gi."
  }
}

variable "voice_agent_request_timeout_seconds" {
  type        = number
  description = "Cloud Run timeout for credit-support-agent control and readiness requests. Live sessions continue in the always-allocated background runtime."
  default     = 300

  validation {
    condition     = var.voice_agent_request_timeout_seconds >= 15 && var.voice_agent_request_timeout_seconds <= 3600
    error_message = "voice_agent_request_timeout_seconds must be between 15 and 3600."
  }
}

variable "voice_agent_min_instances" {
  type        = number
  description = "Minimum warm credit-support-agent instances. Keep at least one because Live sessions outlive their start request."
  default     = 1

  validation {
    condition     = var.voice_agent_min_instances >= 1
    error_message = "voice_agent_min_instances must be at least 1."
  }
}

variable "voice_agent_max_instances" {
  type        = number
  description = "Maximum credit-support-agent instances. Tune only with deployed capacity evidence."
  default     = 5

  validation {
    condition     = var.voice_agent_max_instances >= var.voice_agent_min_instances
    error_message = "voice_agent_max_instances must be at least voice_agent_min_instances."
  }
}

variable "voice_agent_max_concurrent_sessions" {
  type        = number
  description = "Maximum weighted Live session capacity per credit-support-agent instance."
  default     = 4

  validation {
    condition     = var.voice_agent_max_concurrent_sessions >= 1
    error_message = "voice_agent_max_concurrent_sessions must be at least 1."
  }
}

variable "voice_agent_audio_session_capacity_units" {
  type        = number
  description = "Capacity units consumed by one Gemini Live audio session."
  default     = 1

  validation {
    condition = (
      var.voice_agent_audio_session_capacity_units >= 1 &&
      var.voice_agent_audio_session_capacity_units <= var.voice_agent_max_concurrent_sessions
    )
    error_message = "voice_agent_audio_session_capacity_units must be between 1 and the maximum weighted session capacity."
  }
}

variable "voice_agent_video_session_capacity_units" {
  type        = number
  description = "Capacity units consumed by one Live Avatar video session."
  default     = 4

  validation {
    condition = (
      var.voice_agent_video_session_capacity_units >= 1 &&
      var.voice_agent_video_session_capacity_units <= var.voice_agent_max_concurrent_sessions
    )
    error_message = "voice_agent_video_session_capacity_units must be between 1 and the maximum weighted session capacity."
  }
}

variable "data_generator_max_instance_request_concurrency" {
  type        = number
  description = "Maximum concurrent requests per data-generator Cloud Run instance."
  default     = 8
}

variable "data_generator_request_timeout" {
  type        = string
  description = "Timeout for a data-generator request."
  default     = "45s"
}

variable "data_generator_swipe_workflow_concurrency" {
  type        = number
  description = "Maximum number of concurrent swipe workflows dispatched by data-generator."
  default     = 1
}

variable "data_generator_cron_schedule" {
  type        = string
  description = "Cron schedule for background synthetic card activity."
  default     = "* * * * *"
}

variable "fraud_alert_lifecycle_schedule" {
  type        = string
  description = "Cron schedule for expiring stale open synthetic fraud alerts that received no customer response."
  default     = "*/10 * * * *"
}

variable "fraud_alert_no_response_max_age_minutes" {
  type        = number
  description = "Age in minutes after which open synthetic/demo fraud alerts are moved out of OPEN when no customer response arrived."
  default     = 30
}

variable "fraud_alert_lifecycle_batch_limit" {
  type        = number
  description = "Maximum number of open fraud alerts processed by each lifecycle sweep."
  default     = 100
}

variable "data_generator_pulse_window_seconds" {
  type        = number
  description = "Seconds over which each background synthetic card activity pulse is distributed."
  default     = 55
}

variable "data_generator_pulse_min_events" {
  type        = number
  description = "Minimum card events generated by each background synthetic activity pulse."
  default     = 5
}

variable "data_generator_pulse_max_events" {
  type        = number
  description = "Maximum card events generated by each background synthetic activity pulse."
  default     = 10
}

variable "data_generator_swipe_request_timeout_seconds" {
  type        = number
  description = "HTTP timeout in seconds for each synthetic swipe sub-request to banking-service."
  default     = 5
}

variable "data_generator_auto_paydown_max_accounts_per_pulse" {
  type        = number
  description = "Maximum credit accounts evaluated for auto-paydown after each background pulse."
  default     = 2
}

variable "data_generator_fraud_pattern_enabled" {
  type        = bool
  description = "Enable low-rate labeled fraud-pattern traffic during scheduled data-generator pulses."
  default     = false
}

variable "data_generator_fraud_pattern_rate" {
  type        = number
  description = "Probability that an admitted scheduled data-generator pulse includes fraud-pattern traffic when enabled."
  default     = 0.05
}

variable "data_generator_fraud_pattern_max_per_pulse" {
  type        = number
  description = "Maximum labeled fraud-pattern target cards per scheduled data-generator pulse."
  default     = 1
}

variable "data_generator_fraud_pattern_target_mode" {
  type        = string
  description = "Fraud-pattern target selection mode. Use eligible to preserve presenter and VIP exclusions."
  default     = "eligible"
}

variable "data_generator_operator_email_domains" {
  type        = list(string)
  description = "Email domains allowed to call the direct Data Generator operator control surface through IAP."
  default     = ["google.com", "gcp.solutions", "altostrat.com"]
}

variable "data_generator_synthetic_alert_followup_rate" {
  type        = number
  description = "Probability that a synthetic fraud-pattern alert receives a scheduled customer follow-up action."
  default     = 0.65
}

variable "seed_mock_user_count" {
  type        = number
  description = "Target base plus generated mock banking users for algorithmic seeding. VIP/demo-script users are added separately."
  default     = 200
}

variable "full_reset_enabled" {
  type        = bool
  description = "Whether database IAM support users can run the full database reset from the admin GUI."
  default     = false
}

variable "additional_cors_allowed_origins" {
  type        = list(string)
  description = "Additional allowed browser origins for Cloud Run CORS configuration."
  default     = []
}

variable "developer_iam_members" {
  type        = list(string)
  description = "Explicit IAM members that receive developer IAP, Cloud SQL, and governed-data access. Keep the primary member first to preserve legacy Terraform resource addresses."
  default     = []

  validation {
    condition = (
      length(var.developer_iam_members) == length(distinct(var.developer_iam_members)) &&
      alltrue([
        for member in var.developer_iam_members :
        can(regex("^(user|group|serviceAccount):[^[:space:]]+$", member))
      ])
    )
    error_message = "developer_iam_members must contain unique IAM members prefixed with user:, group:, or serviceAccount:."
  }
}

variable "banking_service_timeout_seconds" {
  type        = number
  description = "Timeout in seconds for the banking-service Cloud Run instance."
  default     = 30
}

variable "stable_env_url" {
  type        = string
  description = "URL of the stable environment to show in the test environment banner (leave empty to disable the banner)"
  default     = null
}

variable "feedback_url" {
  type        = string
  description = "URL for the buganizer feedback link to show on the stable environment banner (leave empty to disable)"
  default     = null
}

variable "enable_avatar_modality" {
  type        = bool
  description = "Whether to enable the avatar modality in the banking UI"
  default     = false
}
