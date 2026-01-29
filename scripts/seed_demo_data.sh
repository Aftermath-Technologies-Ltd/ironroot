#!/usr/bin/env bash
# Author: Bradley R. Kinnard
# seeds demo data for local testing
set -e

echo "seeding demo data..."
python -c "from ironroot.storage.postgres import seed_demo_data; seed_demo_data()"
echo "demo data seeded"
