# VeriCode — project overview

**Verify before you trust or generate.** Large language models answer from knowledge that ages. In chat that shows
up as stale facts: versions, prices, laws, deadlines. In coding agents it shows up as code written against APIs that
don't exist, or are deprecated, in the dependency versions actually installed. VeriCode is one verification layer
for both.

## What it does
- **Track 1 — Stale-Answer Detector.** Splits an LLM answer into atomic, span-traceable claims and finds the
  time-sensitive ones. It checks those against live evidence (Tavily) or installed packages, weighs source authority
  and evidence sufficiency, and returns a status per claim with evidence freshness, verification confidence,
  verbatim quotes and a cited corrected answer.
- **Track 2 — Pre-Flight API & Dependency Gatekeeper + token-efficient coding agent.** Before generating code, a
  planner lists the third-party APIs it intends to use. VeriCode verifies each against the installed source (Python
  AST over site-packages; TypeScript compiler API over node_modules, including chained calls) and injects only the
  corrections. The coder then edits a sandboxed copy, tests run, and repairs are bounded. Every token is labelled
  `ACTUAL_PROVIDER_USAGE`, `ESTIMATED` or `MOCK`.

## What makes it different
- **One principle, two tracks, shared machinery.** The installed-package verifiers built for Track 2 are also
  version-specific evidence for Track 1 claims about libraries (Demo E).
- **Ground truth is the installed code**, not model memory and not only the web.
- **Honest measurement.** Mock, estimated and provider-reported tokens are never mixed; savings are computed only
  when both modes succeed on every paired run.
- **Conservative verdicts.** Weak sources can't contradict a claim, old pages are "correct when published", and
  insufficient evidence stays UNVERIFIED.

## Technology
Python 3 · FastAPI · Pydantic v2 · SQLite · httpx · TypeScript compiler API (pinned TS 5.9.3) · React 19 +
TypeScript + Tailwind v4 + Vite · Playwright · Docker (network-less sandbox) · Tavily · Groq via the
OpenAI-compatible API (Anthropic adapter implemented, not live-tested) · GitHub Actions.

## Where to look
- [ARCHITECTURE.md](ARCHITECTURE.md): diagrams
- [TRACK_MAPPING.md](TRACK_MAPPING.md): requirement → feature → evidence
- [DEMO_SCRIPT.md](DEMO_SCRIPT.md): 5–7 minute demo
- [RESULTS_AND_LIMITATIONS.md](RESULTS_AND_LIMITATIONS.md): measured results
- [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md): what is done and what is missing
