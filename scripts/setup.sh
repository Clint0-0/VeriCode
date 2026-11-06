#!/usr/bin/env bash
# One-time setup: backend venv, demo project venv (pydantic 2.9.2), frontend deps + build.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -q -r backend/requirements.txt
python3 -m venv demos/sample_project/.venv
demos/sample_project/.venv/bin/pip install -q "pydantic==2.9.2" pytest
(cd frontend && npm install && npm run build)
[ -f .env ] || cp .env.example .env
echo "Setup complete. Edit .env to add TAVILY_API_KEY and an LLM key, then run scripts/run.sh"
