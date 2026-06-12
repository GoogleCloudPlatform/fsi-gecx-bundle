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

# Package the blocking function source code into a zip archive
data "archive_file" "blocking_function_zip" {
  count       = var.enable_blocking_functions ? 1 : 0
  type        = "zip"
  source_dir  = "${path.module}/../../blocking-function"
  output_path = "${path.module}/blocking-function.zip"
  excludes    = [".gcloudignore", "node_modules"]
}

# Create a storage bucket to store the function source code zip
resource "google_storage_bucket" "blocking_function_bucket" {
  count                       = var.enable_blocking_functions ? 1 : 0
  name                        = "${var.project_id}-blocking-function-source"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

# Upload the zip archive to GCS
resource "google_storage_bucket_object" "blocking_function_zip_object" {
  count  = var.enable_blocking_functions ? 1 : 0
  name   = "blocking-function-${data.archive_file.blocking_function_zip[0].output_md5}.zip"
  bucket = google_storage_bucket.blocking_function_bucket[0].name
  source = data.archive_file.blocking_function_zip[0].output_path
}

resource "google_cloudfunctions2_function" "before_create_function" {
  count       = var.enable_blocking_functions ? 1 : 0
  name        = "gcip-before-create"
  location    = var.region
  description = "GCIP blocking function for email domain restriction (beforeCreate)"

  build_config {
    runtime     = "nodejs22"
    entry_point = "beforeCreate"
    source {
      storage_source {
        bucket = google_storage_bucket.blocking_function_bucket[0].name
        object = google_storage_bucket_object.blocking_function_zip_object[0].name
      }
    }
  }

  service_config {
    max_instance_count = 3
    min_instance_count = 0
    available_memory   = "256M"
    timeout_seconds    = 60
  }

  depends_on = [
    google_project_service.cloudfunctions_googleapis_com,
    google_project_service.run_googleapis_com,
    google_project_service.cloudbuild_googleapis_com,
    google_project_service.artifactregistry_googleapis_com
  ]
}

resource "google_cloudfunctions2_function" "before_sign_in_function" {
  count       = var.enable_blocking_functions ? 1 : 0
  name        = "gcip-before-sign-in"
  location    = var.region
  description = "GCIP blocking function for email domain restriction (beforeSignIn)"

  build_config {
    runtime     = "nodejs22"
    entry_point = "beforeSignIn"
    source {
      storage_source {
        bucket = google_storage_bucket.blocking_function_bucket[0].name
        object = google_storage_bucket_object.blocking_function_zip_object[0].name
      }
    }
  }

  service_config {
    max_instance_count = 3
    min_instance_count = 0
    available_memory   = "256M"
    timeout_seconds    = 60
  }

  depends_on = [
    google_project_service.cloudfunctions_googleapis_com,
    google_project_service.run_googleapis_com,
    google_project_service.cloudbuild_googleapis_com,
    google_project_service.artifactregistry_googleapis_com
  ]
}

# https://www.npmjs.com/package/gcip-cloud-functions#:~:text=allow%20unauthenticated%20invocations
resource "google_cloud_run_service_iam_member" "before_create_invoker" {
  count    = var.enable_blocking_functions ? 1 : 0
  location = google_cloudfunctions2_function.before_create_function[0].location
  project  = google_cloudfunctions2_function.before_create_function[0].project
  service  = google_cloudfunctions2_function.before_create_function[0].service_config[0].service
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# https://www.npmjs.com/package/gcip-cloud-functions#:~:text=allow%20unauthenticated%20invocations
resource "google_cloud_run_service_iam_member" "before_sign_in_invoker" {
  count    = var.enable_blocking_functions ? 1 : 0
  location = google_cloudfunctions2_function.before_sign_in_function[0].location
  project  = google_cloudfunctions2_function.before_sign_in_function[0].project
  service  = google_cloudfunctions2_function.before_sign_in_function[0].service_config[0].service
  role     = "roles/run.invoker"
  member   = "allUsers"
}
