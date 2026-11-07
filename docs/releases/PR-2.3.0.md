# VeriCode 2.3.0 — live validation with Groq + Tavily

Base: `main` (`a655be9`) ← head: `feat/vericode-live-validation`

## What changed
- `backend/vericode/live_validation.py`: live harness, every section labelled ACTUAL_SUCCESS / ACTUAL_FAILED / BLOCKED, no mock fallback, secret scan before writing the report.
- `.github/workflows/live.yml`: manual live workflow (keys from secrets, model and endpoint from variables), `only=` filter, report printed to the log.
- Fix: pre-flight false NOT_FOUND when the planner puts a class in the import path (`pydantic.BaseModel.model_dump`).
- Fix: output truncation detection with one bounded budget increase; clear 429 errors; optional `VERICODE_REASONING_EFFORT`.
- Tests: `backend/tests/test_live_findings.py` (fake transports + real installed pydantic). Offline tests isolated from a developer `.env`.
- Docs: `docs/LIVE_VALIDATION.md`, README (Groq/Tavily setup, live status, actual vs MOCK results, limitations), CHANGELOG 2.3.0.

## Verified
- Key-free CI green on this branch.
- Local: backend 224 passed / 11 skipped (Docker + live), frontend 9 passed, offline demos OK.
- Live (Groq `openai/gpt-oss-120b` + Tavily): see docs/LIVE_VALIDATION.md. Run 42401454502 passed everything except the TypeScript task.

## Not verified
- The two fixes on the live provider: the re-run (42403530801) hit Groq HTTP 429 rate limits.
- Benchmark with per-stage token splits on the fixed code.
- Anthropic provider live.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01MSRYnyXsjZhZowc3XU2sZ6
