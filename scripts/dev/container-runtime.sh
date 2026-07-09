#!/usr/bin/env bash

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
