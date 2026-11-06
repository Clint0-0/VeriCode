#!/usr/bin/env bash
# Serves the API and the built dashboard on http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")/../backend"
exec ../.venv/bin/uvicorn vericode.api:app --host 127.0.0.1 --port "${PORT:-8000}"
