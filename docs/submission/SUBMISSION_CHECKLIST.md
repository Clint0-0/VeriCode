# Submission checklist

Status as of `main` (PR #1 merged by fast-forward, `a655be9..91a889b`). Labels: LOCAL · CI · LIVE · MOCK · BLOCKED.

| Item | Status |
|---|---|
| Project introduction | ✅ README, [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) |
| Problem-statement mapping (both tracks) | ✅ [TRACK_MAPPING.md](TRACK_MAPPING.md), written from **team summaries** |
| Official problem-statement documents | ✅ `docs/problem-statements/track1-ps1.pdf` (Tavily, Stale-answer detector), `track2-ps1.pdf` (Bifrost, fewest-token coding agent) |
| Architecture and workflow diagrams (Mermaid) | ✅ [ARCHITECTURE.md](ARCHITECTURE.md) |
| Setup and run instructions | ✅ README Quick start, `docs/SETUP.md`, `docs/SETUP_WINDOWS.md` |
| API key configuration (Groq via OpenAI-compatible API, Tavily) | ✅ README "Live configuration" |
| Demo instructions and script | ✅ [DEMO_SCRIPT.md](DEMO_SCRIPT.md), `docs/DEMO.md`, `docs/OFFLINE_DEMO.md` |
| Screenshots | ✅ [screenshots/](screenshots/), offline FIXTURE/MOCK data, labelled |
| Track 1 live validation | ✅ LIVE (scenarios A–D, Demo E, judge, Tavily) |
| Track 2 live validation | ✅ LIVE (Python, TypeScript and chained-call TypeScript tasks, Demo C) |
| Chained TypeScript calls on a live plan | ✅ LIVE (8 chains resolved, run 42465099749). The two later false-alarm fixes are LOCAL · CI only |
| Actual-token benchmark v1 (historical) | ✅ LIVE: users 79.6%, summary 49.6%, **signup −139.6%** (VeriCode costs more on this tiny task; run 42491474776) |
| Actual-token benchmark v2 (12 tasks, 3 configurations) | ⚠️ LIVE on 6 of 12 tasks: adaptive 46.0% / original 28.7% token-weighted savings (exploratory, n ≤ 3); signup still negative; 6 tasks + ablation BLOCKED by the Groq daily quota — resume instructions in [benchmark-results/2026-11-13](benchmark-results/2026-11-13/README.md) |
| Anthropic provider | ⚠️ MOCK only (no key) |
| Browser tests | ✅ CI (mock: 9) · LIVE (persisted live data: 6/6) |
| Security review | ✅ LOCAL: secret scan of full history, auth coverage, host check, CORS, command allowlist, sandbox, `npm audit`/`pip-audit` clean. Not a formal certification |
| Local tests, CI | ✅ LOCAL 265 passed · CI green on `main` |
| Results and limitations, future work | ✅ [RESULTS_AND_LIMITATIONS.md](RESULTS_AND_LIMITATIONS.md), README |
| PR #1 | ✅ merged into `main` (fast-forward, no force push) |
