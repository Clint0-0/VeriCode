#!/usr/bin/env bash
# Serves the API and the built dashboard. Binds to 127.0.0.1 unless VERICODE_HOST + VERICODE_ALLOW_REMOTE=1 are set.
set -euo pipefail
cd "$(dirname "$0")/../backend"
HOST="${VERICODE_HOST:-127.0.0.1}"
if [[ "$HOST" != "127.0.0.1" && "$HOST" != "localhost" && "$HOST" != "::1" && "${VERICODE_ALLOW_REMOTE:-0}" != "1" ]]; then
  echo "Refusing to bind to $HOST without VERICODE_ALLOW_REMOTE=1" >&2; exit 1
fi
export VERICODE_HOST="$HOST"
exec ../.venv/bin/uvicorn vericode.api:app --host "$HOST" --port "${PORT:-8000}"
