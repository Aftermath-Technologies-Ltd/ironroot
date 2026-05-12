#!/usr/bin/env bash
# Bring up infrastructure (Postgres, Redis) and initialize schema.
set -e

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

if [ -z "$VIRTUAL_ENV" ]; then
    source .venv/bin/activate
fi

python -c "
from ironroot.storage.postgres import engine, Base
from ironroot.storage.models import *
import asyncio

async def setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

asyncio.run(setup())
"

echo "Infrastructure ready. Start the API with: ./scripts/run_once.sh"
