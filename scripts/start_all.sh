#!/usr/bin/env bash
# Author: Bradley R. Kinnard
# Full system startup: infrastructure + backend + UI
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "╔══════════════════════════════════════════════════╗"
echo "║           IRONROOT System Startup                ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# check for .env
if [ ! -f .env ]; then
    echo "→ Creating .env from .env.example..."
    cp .env.example .env
fi

# start infrastructure
echo "→ Starting PostgreSQL and Redis..."
docker-compose up -d postgres redis

echo "→ Waiting for services to be healthy..."
sleep 5

# check postgres
until docker-compose exec -T postgres pg_isready -U ironroot > /dev/null 2>&1; do
    echo "  waiting for postgres..."
    sleep 2
done
echo "  ✓ PostgreSQL ready"

# check redis
until docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; do
    echo "  waiting for redis..."
    sleep 2
done
echo "  ✓ Redis ready"

# activate venv if not active
if [ -z "$VIRTUAL_ENV" ]; then
    echo "→ Activating virtual environment..."
    source .venv/bin/activate
fi

# run migrations (create tables)
echo "→ Running database setup..."
python -c "
from ironroot.storage.postgres import engine, Base
from ironroot.storage.models import *
import asyncio

async def setup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('  ✓ Database tables created')

asyncio.run(setup())
"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║           Infrastructure Ready                   ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo ""
echo "  1. Start the API server (in this terminal):"
echo "     ./scripts/run_once.sh"
echo ""
echo "  2. Start the UI (in another terminal):"
echo "     cd ui && npm install && npm run dev"
echo ""
echo "  3. Access:"
echo "     API:  http://localhost:8000/docs"
echo "     UI:   http://localhost:3000"
echo ""
