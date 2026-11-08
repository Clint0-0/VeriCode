# VeriCode 2.3.x — live validation with Groq + Tavily (final round)

Base: `main` ← head: `feat/vericode-live-final` (includes all of `feat/vericode-live-validation`).

## Summary
- Live-confirmed: model_dump import-path fix, truncation detection + bounded retry, new Python and TypeScript tasks, Demo C, Track 1 B/D, Demo E, browser pass over persisted live results.
- Track 1: evidence sufficiency (weak sources never contradict), version monotonicity, lexical never overrides stronger evidence, negation-aware value matching, product->publisher aliases.
- Pre-flight: several live false alarms fixed (Python positional values; TS namespace members, member paths, chained calls, empty args, planner-side identifiers).
- Providers: correct rate-limit waits, quota recording, structured-stage reasoning_effort with automatic fallback.
- Tokens: compact planner contract. Actual benchmark `users`: 79.6% savings (n=3).
- Full report: `docs/LIVE_VALIDATION.md`.

## Not done
- Benchmark `summary` + `signup` on optimised code (Groq 429).
- Live confirmation of the chained-member TS fixes (Groq 429).
- Anthropic live (no key).

## Checks
- Key-free CI on this branch.
- Local: backend 248 passed / 11 skipped (Docker + live), frontend 9, mock e2e 6, offline demos 5/5.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01MSRYnyXsjZhZowc3XU2sZ6
