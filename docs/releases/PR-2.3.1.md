# VeriCode 2.3.x — live validation with Groq + Tavily

Base: `main` (`a655be9`) ← head: `feat/vericode-live-final` (contains all of `feat/vericode-live-validation`; fast-forward possible).

## Summary
- **Live harness and workflow**: `vericode.live_validation` runs real Groq (OpenAI-compatible adapter) and Tavily checks in a manual GitHub Actions workflow. Keys come from repo secrets. There is no mock fallback, a quota gate, and a secret scan.
- **Track 1 accuracy**:
  - weak sources never contradict a claim;
  - lexical matches never override stronger evidence;
  - version monotonicity for "latest version" claims;
  - undated pages never override dated ones;
  - negation-aware value matching;
  - product→publisher aliases.
- **Pre-flight fixes for false alarms found live**:
  - Python: class in the import path; positional values for `*args` APIs.
  - TypeScript: namespace members, member paths, chained call results, empty argument lists, planner-side identifiers.
- **Providers**:
  - truncation detection with a bounded retry;
  - correct Groq rate-limit waits;
  - quota recording;
  - structured-stage `reasoning_effort` with automatic fallback.
- **Tokens**: compact planner output contract.
- **Browser**: Playwright over persisted live results (`test_e2e_live.py`).

## Live evidence (Groq `openai/gpt-oss-120b` + Tavily) — details in `docs/LIVE_VALIDATION.md`
| Item | Result |
|---|---|
| Provider probes (text, structured planner, skeleton, streaming usage, truncation, errors) | ACTUAL AND SUCCESSFUL |
| Evidence judge with verbatim quotes | ACTUAL AND SUCCESSFUL |
| Tavily search/extract/persistence | ACTUAL AND SUCCESSFUL |
| Track 1 A–D, Demo E | ACTUAL AND SUCCESSFUL (B → CONTRADICTED 3.14; D → UNVERIFIED) |
| New Python task, new TypeScript task, Demo C | ACTUAL AND SUCCESSFUL |
| Browser over live data | 6/6 (4/4 + 2 skipped in runs without Track 1 data) |
| Chained-call TS pre-flight on a live plan | not exercised live (regression tests only) |
| Anthropic provider | never live-tested (no key) |

## Actual-token benchmark (3 runs per mode)
| Task | Success B / V | Baseline tokens | VeriCode tokens | Savings |
|---|---|---|---|---|
| users | 3/3 / 3/3 | 10,635.7 | 2,169 | 79.6% |
| summary | 3/3 / 3/3 | 3,941.3 | 1,987.7 | 49.6% |
| signup | 3/3 / 2/3 (Groq 429) | 761 | 1,793 (2 runs) | not computed (pairs −127%, −136%) |

Savings come from avoided repairs; on the tiny `signup` task VeriCode's planning overhead roughly doubles the cost. Three small tasks are not a general savings claim.

## Checks
- Key-free CI green on the head commit (backend + Docker sandbox, offline demos, frontend, mock-provider browser e2e).
- Local: see the final validation in the merge comment / `docs/LIVE_VALIDATION.md`.

## Not done
- `signup` savings (blocked by Groq rate limits).
- Anthropic live test.
- Official problem-statement documents are not in the repo.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01MSRYnyXsjZhZowc3XU2sZ6
