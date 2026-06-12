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

variable "additional_cloud_run_iap_members" {
  description = "A list of IAM members to grant the Cloud Run IAP role."
  type        = list(string)
  default     = []
}

variable "ccai_company_id" {
  type = string
}

variable "ccai_host" {
  type = string
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
  default = "https://github.com/cloud-gtm/fsi-gecx-bundle.git"

  validation {
    condition     = var.deploy_cloud_build_triggers ? (var.github_repo_remote_uri != null && var.github_repo_remote_uri != "") : true
    error_message = "github_repo_remote_uri must be provided when deploy_cloud_build_triggers is true."
  }
}

variable "github_connection_name" {
  type    = string
  default = "cloud-gtm"
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

variable "github_branch" {
  type        = string
  description = "The target branch filter for Cloud Build triggers (e.g., ^main$ or ^feature/.*$)"
  default     = "^main$"
}

resource "terraform_data" "validate_blocking_functions" {
  lifecycle {
    precondition {
      condition     = !var.enable_blocking_functions || var.use_external_identities
      error_message = "enable_blocking_functions can only be set to true if use_external_identities is set to true."
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
