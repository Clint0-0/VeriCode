# Setup, running and testing

**Requirements:** Python ≥ 3.11 (tested 3.13), Node ≥ 20 (tested 22), Linux/macOS. `unshare` (util-linux) enables
network-isolated test runs on Linux.

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

**Database:** SQLite at `./vericode.db` (override with `VERICODE_DB`). The schema is created automatically on startup
(`db.init_db()`, idempotent `CREATE TABLE IF NOT EXISTS`). To reset, delete the file.

**Run:** `scripts/run.sh` (API + built UI on :8000). Dev UI: `cd frontend && npm run dev` (:5173).

**Add your own workspace:** put or symlink the project under `demos/` (or set `VERICODE_WORKSPACES`) with its
virtualenv at `.venv` and/or `node_modules` installed, so installed versions can be read.

**Tests:** `scripts/test.sh`
- backend: `.venv/bin/python -m pytest -q backend/tests` (dependency, API-verification, Tavily, stale-answer, agent,
  token, security, memory and API-contract tests; the demo-project tests need `demos/sample_project/.venv`)
- frontend: `cd frontend && npx tsc -b && npx vitest run` (navigation, input, API integration, loading/error/empty states)
