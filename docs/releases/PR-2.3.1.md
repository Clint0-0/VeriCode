# VeriCode 2.3.x — live validation with Groq + Tavily, submission package

Base `main` (`a655be9`) ← head `feat/vericode-live-final` (contains all of `feat/vericode-live-validation`; fast-forward possible). **Do not merge without owner approval.**

## What this PR adds
- **Live validation**: `vericode.live_validation` harness plus a manual GitHub Actions workflow.
  - Groq via the OpenAI-compatible adapter, and Tavily; keys come from repo secrets.
  - No mock fallback; quota gate; secret scan.
  - Quota-stopped work is classified BLOCKED, not FAILED.
- **Track 1 accuracy**:
  - evidence sufficiency: weak sources never contradict; lexical matches never override stronger evidence;
  - version monotonicity for "latest version" claims; undated pages never override dated ones;
  - negation-aware value matching; product→publisher aliases.
- **Track 2 pre-flight**: false alarms found live and fixed, each with regressions.
  - Python: class in the import path; positional values for `*args` APIs.
  - TypeScript: namespace members, member paths, chained call results, root call results (`expect().toThrow()`),
    empty argument lists, planner-side identifiers, task-named local identifiers, instance members through a
    namespace, module-prefixed names.
- **Providers**:
  - truncation detection with a bounded retry;
  - Groq `retry-after` handling with bounded waits and an immediate stop on long caps;
  - quota recording; structured-stage `reasoning_effort` with automatic fallback.
- **Tokens**: compact planner output contract.
- **Security**: runtime introspection runs without network where supported. History secret scan, `npm audit` and
  `pip-audit` are clean.
- **Browser tests**:
  - Playwright over persisted live results;
  - new empty-state, error-state and mock-labelling tests in CI.
- **Docs**:
  - `docs/submission/`: overview, Mermaid diagrams, track mapping, demo script, results and limitations, checklist,
    labelled offline screenshots;
  - README, CHANGELOG, `LIVE_VALIDATION.md`, `BENCHMARK.md`, `ARCHITECTURE.md` reconciled with LOCAL / CI / LIVE /
    MOCK / BLOCKED labels.

## Evidence
| Check | Result |
|---|---|
| Key-free CI (head) | green: backend 265 passed / 2 skipped (live tests, no keys) · Docker sandbox 16 · frontend 9 + typecheck + build · browser (mock) 9 · offline demos 5/5 |
| Local | `scripts/test.sh` 265 passed / 17 skipped (9 Docker: no daemon; 6 live-browser: no live DB; 2 live: no keys) · frontend 9 · offline demos 5/5 |
| LIVE Groq | text, structured planner, skeleton, streaming usage, truncation + retry, errors, rate limits, evidence judge |
| LIVE Tavily | search, extract, dates, retrieval timestamps, credits, persistence |
| LIVE Track 1 | A supported · B CONTRADICTED (correction 3.14) · C supported/quote-less verdict discarded · D UNVERIFIED · Demo E fixed |
| LIVE Track 2 | new Python task ✓ · new TS task ✓ (3,026 tokens) · **chained-call TS task ✓ (2,811 tokens, 8 chains resolved)** · Demo C ✓ |
| LIVE browser | 6/6 over persisted live data |

## Actual-token benchmark (Groq `openai/gpt-oss-120b`, 3 runs per mode)
| Task | Success B / V | Baseline tokens | VeriCode tokens | Savings |
|---|---|---|---|---|
| users | 3/3 / 3/3 | 10,635.7 | 2,169 | 79.6% |
| summary | 3/3 / 3/3 | 3,941.3 | 1,987.7 | 49.6% |
| signup | 3/3 / 2/3 | 761 | 1,793 (2 runs) | **BLOCKED** (Groq 429). Completed pairs −127% / −136% |

Savings come from avoided repairs. On the tiny `signup` task, planning overhead roughly doubles the cost. Three small tasks are not a general savings claim.

## Not done / blockers
- `signup` benchmark: one VeriCode run missing (Groq rate limits).
- The latest three pre-flight false-alarm fixes are verified locally and in CI, not yet on a live plan.
- Anthropic provider never live-tested (no key).
- Official problem-statement documents (Track 1 PS1, Track 2 PS1) are not in the repo.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01MSRYnyXsjZhZowc3XU2sZ6
