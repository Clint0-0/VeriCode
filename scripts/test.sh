#!/usr/bin/env bash
# Unit + integration tests (mocked HTTP for providers). Live tests: VERICODE_LIVE_TESTS=1 scripts/test.sh -m live
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests "$@"
(cd frontend && npx tsc -b && npx vitest run)
