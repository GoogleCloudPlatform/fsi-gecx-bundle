#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE_DIR="${ROOT_DIR}/banking-service"
COMPOSE_FILE="${ROOT_DIR}/compose.shadowdb.yaml"
RUNTIME="$(bash "${ROOT_DIR}/scripts/dev/container-runtime.sh")"
PROJECT_NAME="${SHADOW_DB_PROJECT:-fsi-gecx-shadowdb}"
SHADOW_DB_PORT="${SHADOW_DB_PORT:-55432}"
SHADOW_DB_NAME="${SHADOW_DB_NAME:-banking_shadow}"
SHADOW_DB_USER="${SHADOW_DB_USER:-banking}"
SHADOW_DB_PASSWORD="${SHADOW_DB_PASSWORD:-banking}"
DATABASE_URL="postgresql+psycopg2://${SHADOW_DB_USER}:${SHADOW_DB_PASSWORD}@127.0.0.1:${SHADOW_DB_PORT}/${SHADOW_DB_NAME}"

compose() {
  "${RUNTIME}" compose -f "${COMPOSE_FILE}" -p "${PROJECT_NAME}" "$@"
}

run_alembic() {
  if [[ -x "${SERVICE_DIR}/.venv/bin/alembic" ]]; then
    (
      cd "${SERVICE_DIR}"
      ALEMBIC_RUNNING=true DATABASE_URL="${DATABASE_URL}" ./.venv/bin/alembic "$@"
    )
    return
  fi

  (
    cd "${SERVICE_DIR}"
    ALEMBIC_RUNNING=true DATABASE_URL="${DATABASE_URL}" uv run alembic "$@"
  )
}

wait_for_db() {
  local attempts=30
  local i
  for ((i=1; i<=attempts; i++)); do
    if compose exec -T shadow-db pg_isready -U "${SHADOW_DB_USER}" -d "${SHADOW_DB_NAME}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Shadow database did not become ready in time." >&2
  exit 1
}

ensure_up() {
  compose up -d shadow-db
  wait_for_db
}

usage() {
  cat <<'EOF'
Usage: bash scripts/dev/alembic-shadow.sh <command> [args]

Commands:
  up                    Start the local-only PostgreSQL shadow database
  down                  Stop and remove the local-only shadow database
  logs                  Tail shadow database logs
  current               Show Alembic current revision against the shadow database
  upgrade               Run alembic upgrade head against the shadow database
  revision <message>    Autogenerate a new Alembic revision against the shadow database
EOF
}

command_name="${1:-}"
if [[ -z "${command_name}" ]]; then
  usage
  exit 1
fi
shift || true

case "${command_name}" in
  up)
    ensure_up
    ;;
  down)
    compose down
    ;;
  logs)
    compose logs -f shadow-db
    ;;
  current)
    ensure_up
    run_alembic current
    ;;
  upgrade)
    ensure_up
    run_alembic upgrade head
    ;;
  revision)
    if [[ $# -eq 0 ]]; then
      echo "Revision message is required." >&2
      exit 1
    fi
    ensure_up
    run_alembic upgrade head
    run_alembic revision --autogenerate -m "$*"
    ;;
  *)
    usage
    exit 1
    ;;
esac
