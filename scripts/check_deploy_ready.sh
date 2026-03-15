#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
PARENT_DIR="$(cd "$ROOT_DIR/.." && pwd)"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file not found at $ENV_FILE"
    echo "Run: cp .env.example .env"
    exit 1
fi

get_env_value() {
    local key="$1"
    grep -E "^${key}=" "$ENV_FILE" | head -n1 | cut -d= -f2- || true
}

require_value() {
    local key="$1"
    local value
    value="$(get_env_value "$key")"
    if [[ -z "$value" ]]; then
        echo "ERROR: $key is empty in .env"
        exit 1
    fi
}

warn_if_default() {
    local key="$1"
    local default_value="$2"
    local value
    value="$(get_env_value "$key")"
    if [[ "$value" == "$default_value" ]]; then
        echo "WARNING: $key is still using the default value"
    fi
}

require_value "SECRET_KEY"
require_value "SUPERADMIN_PASSWORD"
require_value "PUBLIC_BASE_URL"
require_value "ADMINS"
require_value "DB_USER"
require_value "DB_PASS"
require_value "DB_NAME"
require_value "DB_HOST"
require_value "DB_PORT"
require_value "ip"

warn_if_default "SECRET_KEY" "change-me"
warn_if_default "SUPERADMIN_PASSWORD" "change-me-now"
warn_if_default "PUBLIC_BASE_URL" "http://localhost:8000"

platform_dir="$(get_env_value "PLATFORM_DIR")"
platform_dockerfile="$(get_env_value "PLATFORM_DOCKERFILE")"

if [[ -z "$platform_dir" ]]; then
    platform_dir="rentbot_platform"
fi

if [[ -z "$platform_dockerfile" ]]; then
    platform_dockerfile="rentbot_platform/Dockerfile"
fi

if [[ "$(basename "$ROOT_DIR")" != "$platform_dir" ]]; then
    echo "ERROR: repo folder name is '$(basename "$ROOT_DIR")' but PLATFORM_DIR is '$platform_dir'"
    exit 1
fi

if [[ ! -f "$PARENT_DIR/app.py" ]]; then
    echo "ERROR: legacy bot entrypoint not found at $PARENT_DIR/app.py"
    echo "Expected layout: <legacy-repo-root>/$platform_dir"
    exit 1
fi

if [[ ! -f "$PARENT_DIR/requirements.txt" ]]; then
    echo "ERROR: legacy requirements.txt not found at $PARENT_DIR/requirements.txt"
    exit 1
fi

if [[ ! -f "$ROOT_DIR/Dockerfile" ]]; then
    echo "ERROR: Dockerfile not found at $ROOT_DIR/Dockerfile"
    exit 1
fi

if [[ "$platform_dockerfile" != "$platform_dir/Dockerfile" ]]; then
    echo "WARNING: PLATFORM_DOCKERFILE is '$platform_dockerfile'"
    echo "Make sure docker-compose.yml can reach this path from the legacy repo root."
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker is not installed"
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: docker compose plugin is not available"
    exit 1
fi

echo "OK: deploy prerequisites look good"
echo "Next step: docker compose up --build -d"
