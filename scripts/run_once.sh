#!/usr/bin/env bash
# Author: Bradley R. Kinnard
# runs the api once (foreground, no docker)
set -e

export IRONROOT_DEBUG=true
uvicorn ironroot.main:app --reload --host 0.0.0.0 --port 8000
