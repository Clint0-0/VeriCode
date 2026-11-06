#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests
(cd frontend && npx tsc -b && npx vitest run)
