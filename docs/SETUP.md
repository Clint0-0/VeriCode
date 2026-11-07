# Setup, running and testing

**Requirements:** Python ≥ 3.11 (tested 3.13), Node ≥ 20 (tested 22), Linux/macOS. Docker (recommended) enables the
container sandbox. No image pull is needed; VeriCode builds a tiny local base image. Without Docker, `unshare`
(util-linux) gives network-isolated process runs on Linux.

```bash
scripts/setup.sh        # creates .venv, demos/sample_project/.venv (pydantic==2.9.2 + pytest), builds frontend, copies .env.example → .env
```

Manual equivalent:
```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
python3 -m venv demos/sample_project/.venv && demos/sample_project/.venv/bin/pip install pydantic==2.9.2 pytest
cd frontend && npm install && npm run build
```

**Configure** `.env` (see `.env.example`): `TAVILY_API_KEY`, then either `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
(+ `OPENAI_BASE_URL` for compatible gateways), plus `VERICODE_CODER_MODEL` (and optionally `VERICODE_PLANNER_MODEL`,
e.g. a smaller model). No model ids are hardcoded.

**Database:** SQLite at `./vericode.db` (override with `VERICODE_DB`). The schema is created on startup, and
versioned migrations (`db.MIGRATIONS`, tracked in `schema_version`) are applied in order. Settings changed in the UI
are stored in the `settings` table and reloaded on start. Task history, analyses, evidence, rules and benchmarks
survive restarts. To reset, delete the file.

**Run:** `scripts/run.sh` (API + built UI on :8000). Dev UI: `cd frontend && npm run dev` (:5173).

**Add your own workspace:** put or symlink the project under `demos/` (or set `VERICODE_WORKSPACES`) with its
virtualenv at `.venv` and/or `node_modules` installed, so installed versions can be read.

**Login:** `scripts/run.sh` prints `http://127.0.0.1:8000/?token=…`. Set `VERICODE_AUTH_TOKEN` for a fixed token.
API scripts can send `Authorization: Bearer <token>`.

**Live integration tests** (real network and credentials, never mocked):
`VERICODE_LIVE_TESTS=1 .venv/bin/python -m pytest backend/tests -m live`. They are skipped automatically when
`TAVILY_API_KEY`, or an LLM key plus `VERICODE_CODER_MODEL`, are missing.

**Sandbox test matrix:** `VERICODE_TEST_SANDBOX=docker scripts/test.sh` runs every agent test inside containers.

**Browser e2e tests:** `.venv/bin/python -m pytest backend/tests/test_e2e_ui.py`. These start a real uvicorn
server with a temp DB and drive Chromium through login, Track 1, the combined workflow, the pre-flight heatmap,
a coding task, all 8 screens and the mobile layout. Requires `backend/requirements-dev.txt` (Playwright), a system
Chrome/Chromium and a built frontend. Skipped otherwise.

**Tests:** `scripts/test.sh`
- backend: `.venv/bin/python -m pytest -q backend/tests` (dependency, API-verification, Tavily, stale-answer, agent,
  token, security, memory and API-contract tests; the demo-project tests need `demos/sample_project/.venv`)
- frontend: `cd frontend && npx tsc -b && npx vitest run` (navigation, input, API integration, loading/error/empty states)
