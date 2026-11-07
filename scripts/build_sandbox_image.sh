#!/usr/bin/env bash
# Builds the optional self-contained sandbox image (requires pulling python:3.13-slim once).
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -f docker/sandbox.Dockerfile -t "${VERICODE_SANDBOX_IMAGE:-vericode-sandbox:full}" docker
echo "Built ${VERICODE_SANDBOX_IMAGE:-vericode-sandbox:full}. VeriCode will use it automatically (no host /usr mount)."
