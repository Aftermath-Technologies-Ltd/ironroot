#!/usr/bin/env bash
# Author: Bradley R. Kinnard
# stops the dev environment
set -e

echo "stopping ironroot dev environment..."
docker-compose down
echo "dev environment stopped"
