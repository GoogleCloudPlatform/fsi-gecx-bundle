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

resource "local_file" "gecx_environment" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  filename = "${path.module}/../../gecx/${var.gecx_agent_folder}/environment.json"
  content = templatefile(
    "${path.module}/../../gecx/${var.gecx_agent_folder}/environment.json.tftpl",
    {
      banking_service_url    = google_cloud_run_v2_service.banking_service[0].urls[0]
      gcs_site_data_store_id = google_discovery_engine_data_store.gcs_site.id
    }
  )
}

resource "local_file" "gecx_credit_support_toolset" {
  count    = var.deploy_cloud_run_services ? 1 : 0
  filename = "${path.module}/../../gecx/Credit_Support_Voice_Agent/toolsets/banking_service_mcp_toolset/banking_service_mcp_toolset.yaml"
  content = templatefile(
    "${path.module}/../../gecx/Credit_Support_Voice_Agent/toolsets/banking_service_mcp_toolset/banking_service_mcp_toolset.yaml.tftpl",
    {
      banking_service_url = google_cloud_run_v2_service.banking_service[0].uri
    }
  )
}
