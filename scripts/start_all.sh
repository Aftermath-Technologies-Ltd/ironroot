#!/usr/bin/env bash
# Bring up infrastructure (Postgres, Redis) and migrate the schema.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

if [ ! -f .env ]; then
    cp .env.example .env
fi

docker-compose up -d postgres redis

until docker-compose exec -T postgres pg_isready -U ironroot > /dev/null 2>&1; do
    sleep 2
done

until docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; do
    sleep 2
done

if [ -z "${VIRTUAL_ENV:-}" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

# Migrations are the only allowed way to create or evolve the schema.
# `Base.metadata.create_all` is forbidden outside test fixtures.
alembic upgrade head

echo "Infrastructure ready. Start the API with: ./scripts/run_once.sh"
