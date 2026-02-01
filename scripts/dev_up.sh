#!/usr/bin/env bash
# Author: Bradley R. Kinnard
# starts the dev environment
set -e

echo "starting ironroot dev environment..."
docker-compose up -d postgres redis
echo "waiting for services..."
sleep 3
echo "dev environment ready"
