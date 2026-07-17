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

project_id                    = "fsi-gecx-2000"
alloydb_availability_type     = "ZONAL"
alloydb_cpu_count             = 2
cloudbuild_source_bucket_name = "fsi-gecx-2000_cloudbuild"
release_manifest_reader_members = [
  "serviceAccount:cloudbuild-terraform-sa@fsi-demo-1841.iam.gserviceaccount.com",
]
release_image_consumer_members = [
  "serviceAccount:cloudbuild-terraform-sa@fsi-demo-1841.iam.gserviceaccount.com",
  "serviceAccount:service-628355276832@serverless-robot-prod.iam.gserviceaccount.com",
  "serviceAccount:banking-service-sa@fsi-demo-1841.iam.gserviceaccount.com",
  "serviceAccount:voice-agent-sa@fsi-demo-1841.iam.gserviceaccount.com",
  "serviceAccount:datagen-service-sa@fsi-demo-1841.iam.gserviceaccount.com",
  "serviceAccount:banking-db-migration-sa@fsi-demo-1841.iam.gserviceaccount.com",
  "serviceAccount:banking-db-reset-sa@fsi-demo-1841.iam.gserviceaccount.com",
]
deploy_cloud_build_triggers                     = true
deploy_cloud_run_services                       = true
set_cloud_run_audiences                         = true
ccai_company_id                                 = "17762261086439462b8f0b64f6cd0d5e3"
ccai_host                                       = "https://fsi-test-4000-jz3ioz1.uc1.ccaiplatform.com"
custom_domain                                   = "banking.mservidio.demo.altostrat.com"
github_app_installation_id                      = "261964"
github_oauth_token_secret_name                  = "GoogleCloudPlatform-github-oauthtoken-a845c6"
manage_github_connection                        = false
cx_agent_studio_deployment_name                 = "projects/fsi-gecx-2000/locations/us/apps/e0b952c1-280d-41d0-8da5-46db4b0e6ad9/deployments/ca77d6f4-b7c2-4007-b6c0-51d905132e41"
cx_agent_studio_upload_tool_name                = "projects/fsi-gecx-2000/locations/us/apps/e0b952c1-280d-41d0-8da5-46db4b0e6ad9/tools/7d1d2879-9909-42a5-a39b-4ac6370980d3"
cx_agent_studio_populate_content_tool_name      = "projects/fsi-gecx-2000/locations/us/apps/e0b952c1-280d-41d0-8da5-46db4b0e6ad9/tools/8e42a29a-d20e-4aba-8ea9-beecb68c6a60"
cx_agent_studio_get_user_location_tool_name     = "projects/fsi-gecx-2000/locations/us/apps/e0b952c1-280d-41d0-8da5-46db4b0e6ad9/tools/692fbf88-0560-4a43-a700-ebb82122cd85"
use_external_identities                         = false
enable_blocking_functions                       = false
voice_agent_video_model                         = "publishers/google/models/gemini-3.1-flash-live-preview-04-2026"
voice_agent_audio_model                         = "publishers/google/models/gemini-live-2.5-flash-native-audio"
cx_agent_studio_voice_agent_deployment_name     = "projects/fsi-gecx-2000/locations/us/apps/1c69bee5-af7d-40ff-a83f-012430d1e423/deployments/81b3e89e-31ff-4be9-93ae-f0c99e59d5e0"
stable_env_url                                  = "https://agentic-finance.gcp-solutions.com/"
data_generator_max_instance_request_concurrency = 8
data_generator_request_timeout                  = "120s"
data_generator_swipe_workflow_concurrency       = 1
data_generator_cron_schedule                    = "* * * * *"
data_generator_pulse_window_seconds             = 55
data_generator_pulse_min_events                 = 5
data_generator_pulse_max_events                 = 10
data_generator_fraud_pattern_enabled            = false
data_generator_fraud_pattern_rate               = 0.05
data_generator_fraud_pattern_max_per_pulse      = 1
data_generator_fraud_pattern_target_mode        = "eligible"
seed_mock_user_count                            = 2000
full_reset_enabled                              = true
enable_avatar_modality                          = true
console_viewer_group_join_url                   = "https://groups.google.com/a/google.com/g/fsi-nova-horizon-demo-console-viewer"
