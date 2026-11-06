#!/usr/bin/env bash
# One-time setup: backend venv, demo projects, TypeScript checker, frontend build, .env
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -q -r backend/requirements.txt
python3 -m venv demos/sample_project/.venv
demos/sample_project/.venv/bin/pip install -q "pydantic==2.9.2" pytest
(cd tools/ts-checker && npm ci --no-audit --no-fund)       # VeriCode's pinned TypeScript (compiler API)
(cd demos/ts_project && npm ci --no-audit --no-fund)       # zod 3.23.8 demo project
(cd frontend && npm ci --no-audit --no-fund && npm run build)
[ -f .env ] || cp .env.example .env                        # never overwrites an existing .env
echo "Setup complete. Add TAVILY_API_KEY and ANTHROPIC_API_KEY/OPENAI_API_KEY + VERICODE_CODER_MODEL to .env, then scripts/run.sh"
