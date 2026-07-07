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

resource "google_bigquery_dataset" "ci" {
  dataset_id = "ci"
  location   = "US"
}

resource "google_bigquery_table" "build_version" {
  dataset_id          = google_bigquery_dataset.ci.dataset_id
  table_id            = "build_version"
  schema              = file("${path.module}/../bigquery/ci/table/build_version.json")
  deletion_protection = false
}

resource "google_bigquery_table" "latest_build_version" {
  dataset_id          = google_bigquery_dataset.ci.dataset_id
  table_id            = "latest_build_version"
  deletion_protection = false

  view {
    query          = file("${path.module}/../bigquery/ci/view/latest_build_version.sql")
    use_legacy_sql = false
  }

  depends_on = [google_bigquery_table.build_version]
}

resource "google_bigquery_table" "lines_of_code" {
  dataset_id          = google_bigquery_dataset.ci.dataset_id
  table_id            = "lines_of_code"
  deletion_protection = false

  view {
    query          = file("${path.module}/../bigquery/ci/view/lines_of_code.sql")
    use_legacy_sql = false
  }

  depends_on = [google_bigquery_table.build_version, google_bigquery_table.latest_build_version]
}

resource "google_bigquery_routine" "get_build_version" {
  dataset_id      = google_bigquery_dataset.ci.dataset_id
  routine_id      = "get_build_version"
  routine_type    = "PROCEDURE"
  language        = "SQL"
  definition_body = file("${path.module}/../bigquery/ci/routine/get_build_version.sql")

  arguments {
    name      = "p_application"
    data_type = "{\"typeKind\" :  \"STRING\"}"
  }
  arguments {
    name      = "p_environment"
    data_type = "{\"typeKind\" :  \"STRING\"}"
  }
  arguments {
    name      = "p_version"
    data_type = "{\"typeKind\" :  \"STRING\"}"
  }
  arguments {
    name      = "p_repository"
    data_type = "{\"typeKind\" :  \"STRING\"}"
  }
  arguments {
    name      = "p_commit_sha"
    data_type = "{\"typeKind\" :  \"STRING\"}"
  }
  arguments {
    name      = "p_is_release"
    data_type = "{\"typeKind\" :  \"BOOL\"}"
  }
  arguments {
    name      = "p_linguist_result"
    data_type = "{\"typeKind\" :  \"STRING\"}"
  }
}
