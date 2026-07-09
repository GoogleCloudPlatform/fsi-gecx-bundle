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

resource "google_project_iam_custom_role" "cloud_build_job_runner" {
  role_id     = "custom.cloudbuild.jobCreator"
  title       = "Cloud Build Job Runner"
  description = "Allows triggering Cloud Build builds"
  permissions = ["cloudbuild.builds.create"]
}

locals {
  demo_viewer_custom_role_config = yamldecode(file("${path.module}/config/demo_viewer_custom_role.yaml"))
}

resource "google_project_iam_custom_role" "demo_viewer" {
  role_id     = local.demo_viewer_custom_role_config.role_id
  title       = local.demo_viewer_custom_role_config.title
  description = local.demo_viewer_custom_role_config.description
  permissions = local.demo_viewer_custom_role_config.permissions
}
