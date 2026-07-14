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

# WARNING: Do NOT place any secrets (passwords, private keys, API keys, OAuth tokens)
# in this file. Secrets should be stored in Secret Manager and accessed dynamically.

project_id                                       = "evo-genai-workspace"
deploy_cloud_build_triggers                      = true
deploy_cloud_run_services                        = true
set_cloud_run_audiences                          = true
ccai_company_id                                  = "17762261086439462b8f0b64f6cd0d5e3"
ccai_host                                        = "https://fsi-test-4000-jz3ioz1.uc1.ccaiplatform.com"
custom_domain                                    = "banking.erikvoit.demo.altostrat.com"
github_app_installation_id                       = "261964"
github_oauth_token_secret_name                   = "GoogleCloudPlatform-github-oauthtoken-6a4506"
manage_github_connection                         = false
cx_agent_studio_deployment_name                  = "projects/evo-genai-workspace/locations/us/apps/a3e14f8f-8ac8-4020-94f9-dd7d53294566/deployments/b732b1ca-13be-47f0-8161-250e531c1aa6"
cx_agent_studio_upload_tool_name                 = "projects/evo-genai-workspace/locations/us/apps/a3e14f8f-8ac8-4020-94f9-dd7d53294566/tools/7d1d2879-9909-42a5-a39b-4ac6370980d3"
cx_agent_studio_populate_content_tool_name       = "projects/evo-genai-workspace/locations/us/apps/a3e14f8f-8ac8-4020-94f9-dd7d53294566/tools/8e42a29a-d20e-4aba-8ea9-beecb68c6a60"
use_external_identities                          = true
enable_blocking_functions                        = true
enable_current_user_grants                       = true
repo_branch_expression                           = "^main$"
cloud_build_trigger_event                        = "push_to_branch"
github_repo_remote_uri                           = "https://github.com/GoogleCloudPlatform/fsi-gecx-bundle.git"
github_connection_name                           = "GoogleCloudPlatform"
voice_agent_video_model                          = "publishers/google/models/gemini-3.1-flash-live-preview-04-2026"
voice_agent_audio_model                          = "publishers/google/models/gemini-live-2.5-flash-native-audio"
cx_agent_studio_voice_agent_deployment_name      = "42345105-29cb-492d-8a60-07171bb72190"
banking_service_db_pool_size                     = 24
banking_service_db_max_overflow                  = 16
banking_service_db_pool_timeout                  = 5
banking_service_max_instance_request_concurrency = 32
data_generator_max_instance_request_concurrency  = 8
data_generator_request_timeout                   = "120s"
data_generator_swipe_workflow_concurrency        = 1
data_generator_cron_schedule                     = "* * * * *"
data_generator_pulse_window_seconds              = 55
data_generator_pulse_min_events                  = 5
data_generator_pulse_max_events                  = 10
data_generator_fraud_pattern_enabled             = false
data_generator_fraud_pattern_rate                = 0.05
data_generator_fraud_pattern_max_per_pulse       = 1
data_generator_fraud_pattern_target_mode         = "eligible"
seed_mock_user_count                             = 2000
full_reset_enabled                               = true
stable_env_url                                   = "https://agentic-finance.gcp-solutions.com/"
additional_cors_allowed_origins                  = []
enable_avatar_modality                           = true
