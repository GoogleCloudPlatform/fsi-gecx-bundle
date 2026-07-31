#!/usr/bin/env bash
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


set -euo pipefail

if [[ -n "${CONTAINER_RUNTIME:-}" ]]; then
  echo "${CONTAINER_RUNTIME}"
  exit 0
fi

if command -v docker >/dev/null 2>&1; then
  echo "docker"
  exit 0
fi

if command -v podman >/dev/null 2>&1; then
  echo "podman"
  exit 0
fi

echo "No supported container runtime found. Install Docker or Podman, or set CONTAINER_RUNTIME." >&2
exit 1
