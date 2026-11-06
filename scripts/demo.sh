#!/usr/bin/env bash
# Usage: scripts/demo.sh 1|2|3|all [--live] [--runs N]
set -euo pipefail
cd "$(dirname "$0")/../backend"
exec ../.venv/bin/python -m vericode.demo "$@"
