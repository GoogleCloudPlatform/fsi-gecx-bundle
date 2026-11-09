# shellcheck shell=bash
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

# Release-controller refusal paths, sourced by run_alloydb_release.sh and
# exercised directly by test_release_retention_lib.py with stub gcloud/gsutil.
# Every refusal prints to stderr and exits non-zero.

_release_scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prints the digest an image reference resolves to, or nothing when the
# registry reports it does not exist. Any other describe failure (permission,
# network, quota) fails closed so callers never mistake it for "tag absent".
retention_tag_digest() {
  local reference="$1"
  local stderr_file digest
  stderr_file="$(mktemp)"
  if digest="$(gcloud artifacts docker images describe "${reference}" \
    --format='value(image_summary.digest)' 2>"${stderr_file}")"; then
    rm -f "${stderr_file}"
    printf '%s' "${digest}"
    return 0
  fi
  if grep -qE 'Image not found|NOT_FOUND' "${stderr_file}"; then
    rm -f "${stderr_file}"
    return 0
  fi
  echo "Could not resolve ${reference}:" >&2
  cat "${stderr_file}" >&2
  rm -f "${stderr_file}"
  return 1
}

_release_retention_tag() {
  python3 "${_release_scripts_dir}/voice_release_metadata.py" release-tag \
    --commit "$1" --image "$2"
}

# Qualification: tag a pinned digest release-<commit12>-<digest12> so the
# Artifact Registry KEEP policy retains it. Never moves an existing tag: tags
# may be immutable, and a moved tag would silently drop retention from the
# digest an older manifest pinned.
protect_release_image() {
  local commit="$1"
  local image="$2"
  local repository="${image%@*}"
  local digest="${image##*@}"
  local tag current
  tag="$(_release_retention_tag "${commit}" "${image}")" || exit 1
  current="$(retention_tag_digest "${repository}:${tag}")" || exit 1
  if [[ -z "${current}" ]]; then
    gcloud artifacts docker tags add "${image}" "${repository}:${tag}" --quiet || exit 1
    current="$(retention_tag_digest "${repository}:${tag}")" || exit 1
  fi
  [[ "${current}" == "${digest}" ]] || {
    echo "Retention tag ${repository}:${tag} resolves to '${current}', expected ${digest}" >&2
    exit 1
  }
}

# Promotion: read-only proof that qualification protected the digest in the
# source registry. Never writes tags.
require_release_retention() {
  local commit="$1"
  local image="$2"
  local tag current
  tag="$(_release_retention_tag "${commit}" "${image}")" || exit 1
  current="$(retention_tag_digest "${image%@*}:${tag}")" || exit 1
  [[ "${current}" == "${image##*@}" ]] || {
    echo "Qualified image ${image} lacks retention tag ${tag}; re-qualify ${commit} before promotion." >&2
    exit 1
  }
}

# Downloads the rollback manifest and sets rollback_manifest_args for
# voice_release_metadata.py rollback-target. Only the exact NONE sentinel skips
# the download; voice_release_metadata.py then requires
# ALLOW_NO_ROLLBACK_TARGET=true.
fetch_rollback_manifest() {
  local uri="$1"
  local destination="$2"
  # shellcheck disable=SC2034  # consumed by run_alloydb_release.sh
  rollback_manifest_args=()
  [[ "${uri}" == "NONE" ]] && return 0
  gsutil cp "${uri}" "${destination}" || exit 1
  # shellcheck disable=SC2034  # consumed by run_alloydb_release.sh
  rollback_manifest_args=(--manifest "${destination}")
}
