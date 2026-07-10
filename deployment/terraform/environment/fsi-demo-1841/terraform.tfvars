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

project_id                                  = "fsi-demo-1841"
deploy_cloud_build_triggers                 = true
deploy_cloud_run_services                   = true
set_cloud_run_audiences                     = true
custom_domain                               = "agentic-finance.gcp-solutions.com"
enable_ccai                                 = false
github_app_installation_id                  = "261964"
github_oauth_token_secret_name              = "GoogleCloudPlatform-github-oauthtoken-8efcac"
manage_github_connection                    = false
cx_agent_studio_deployment_name             = "projects/fsi-demo-1841/locations/us/apps/a1814f33-22f7-4b55-a1d2-cb53f236eb4e/deployments/e1200a5a-c9a4-4a4f-9a42-369d5c49cc2a"
cx_agent_studio_upload_tool_name            = "projects/fsi-demo-1841/locations/us/apps/a1814f33-22f7-4b55-a1d2-cb53f236eb4e/tools/7d1d2879-9909-42a5-a39b-4ac6370980d3"
cx_agent_studio_populate_content_tool_name  = "projects/fsi-demo-1841/locations/us/apps/a1814f33-22f7-4b55-a1d2-cb53f236eb4e/tools/8e42a29a-d20e-4aba-8ea9-beecb68c6a60"
cx_agent_studio_get_user_location_tool_name = "projects/fsi-demo-1841/locations/us/apps/a1814f33-22f7-4b55-a1d2-cb53f236eb4e/tools/692fbf88-0560-4a43-a700-ebb82122cd85"
use_external_identities                     = false
enable_blocking_functions                   = false
cloud_build_trigger_event                   = "push_to_branch"
repo_branch_expression                      = "^main$"
voice_agent_video_model                     = "publishers/google/models/gemini-3.1-flash-live-preview-04-2026"
voice_agent_audio_model                     = "publishers/google/models/gemini-live-2.5-flash-native-audio"
cx_agent_studio_voice_agent_deployment_name = "projects/fsi-demo-1841/locations/us/apps/94eea51e-bbb8-4df0-8a8d-7d17b954a00c/deployments/28ad2991-1c10-4247-8070-4ba1b9edd479"
