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

resource "google_artifact_registry_repository" "fsi_gecx_bundle" {
  repository_id = "fsi-gecx-bundle"
  location      = var.region
  format        = "DOCKER"
  description   = "FSI GECX Bundle Docker repository"

  cleanup_policies {
    id     = "keep-latest-10"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  # Digests pinned by a qualify manifest are tagged release-<commit>-<digest>
  # by deployment/scripts/run_alloydb_release.sh. They remain rollback targets
  # and may serve promoted environments that pull from this registry, so they
  # must survive the age-based DELETE below (KEEP takes precedence).
  cleanup_policies {
    id     = "keep-release-pinned"
    action = "KEEP"
    condition {
      tag_state    = "TAGGED"
      tag_prefixes = ["release-"]
    }
  }

  cleanup_policies {
    id     = "delete-older-than-30-days"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "2592000s"
    }
  }

  depends_on = [google_project_service.artifactregistry_googleapis_com]
}
