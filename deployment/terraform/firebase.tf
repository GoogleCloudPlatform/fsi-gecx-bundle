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

resource "google_firebase_project" "default" {
  provider = google-beta
  project  = data.google_project.project.project_id

  depends_on = [google_project_service.firebase_googleapis_com]
}

resource "google_firebase_web_app" "banking_ui_app" {
  provider     = google-beta
  project      = google_firebase_project.default.project
  display_name = "Banking UI"
}

data "google_firebase_web_app_config" "banking_ui_app_config" {
  provider   = google-beta
  project    = google_firebase_project.default.project
  web_app_id = google_firebase_web_app.banking_ui_app.app_id
}

# terraform import google_identity_platform_config.default projects/fsi-gecx-2000/config
resource "google_identity_platform_config" "default" {
  provider = google.google_billing

  authorized_domains = [
    "localhost",
    var.custom_domain,
    "iap.googleapis.com"
  ]

  dynamic "blocking_functions" {
    for_each = var.enable_blocking_functions ? [1] : []
    content {
      triggers {
        event_type   = "beforeCreate"
        function_uri = google_cloudfunctions2_function.before_create_function[0].service_config[0].uri
      }

      triggers {
        event_type   = "beforeSignIn"
        function_uri = google_cloudfunctions2_function.before_sign_in_function[0].service_config[0].uri
      }

      forward_inbound_credentials {
        refresh_token = false
        access_token  = false
        id_token      = false
      }
    }
  }

  lifecycle {
    ignore_changes = [
      multi_tenant
    ]
  }

  depends_on = [
    google_project_service.identitytoolkit_googleapis_com
  ]
}

resource "google_identity_platform_default_supported_idp_config" "google_idp" {
  provider      = google.google_billing
  idp_id        = "google.com"
  enabled       = true
  client_id     = data.google_secret_manager_secret_version_access.iap_client_id.secret_data
  client_secret = data.google_secret_manager_secret_version_access.iap_client_secret.secret_data

  depends_on = [
    google_identity_platform_config.default
  ]
}

resource "google_firebase_hosting_site" "default" {
  provider = google-beta
  site_id  = data.google_project.project.project_id
  app_id   = google_firebase_web_app.banking_ui_app.app_id
}
