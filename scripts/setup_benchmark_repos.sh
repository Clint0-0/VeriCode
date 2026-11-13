#!/usr/bin/env bash
# Install the pinned dependencies of every benchmark repository (demos/*). Idempotent.
#   Python repos: a project-local .venv with the pinned requirements (VeriCode inspects these installed packages)
#   TypeScript repos: npm ci from the committed package-lock.json
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}

py_repo() {  # dir, pip args...
  local dir=$1; shift
  [ -x "demos/$dir/.venv/bin/python" ] || "$PY" -m venv "demos/$dir/.venv"
  "demos/$dir/.venv/bin/pip" install -q "$@"
  echo "ok  demos/$dir ($("demos/$dir/.venv/bin/python" -c 'import pydantic; print("pydantic", pydantic.VERSION)'))"
}

py_repo sample_project "pydantic==2.9.2" pytest
py_repo py_inventory -r demos/py_inventory/requirements.txt
py_repo py_ledger -r demos/py_ledger/requirements.txt
for d in ts_project ts_orders; do
  npm ci --prefix "demos/$d" --no-audit --no-fund --loglevel=error
  echo "ok  demos/$d (zod $(node -p "require('./demos/$d/node_modules/zod/package.json').version"))"
done
