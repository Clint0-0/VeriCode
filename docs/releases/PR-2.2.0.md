# Pull request: `feat/vericode-offline-hardening` → `main`

**Title:** VeriCode 2.1 + 2.2: final validation + offline hardening

## Summary
This brings `main` (currently 2.0.0, `e823809`) up to date with the final-validation (2.1.0) and offline-hardening
(2.2.0) work. **Nothing here requires API keys**; live Tavily and LLM validation is still pending credentials.

### 2.1.0 — final validation
- Combined Track 1 × Track 2 workflow: claims about installed libraries are checked against the installed source (`installed_source` evidence).
- Auto-correction tracking, confidence heatmap, provider streaming, per-model cost, browser e2e tests, demos C and E.

### 2.2.0 — offline hardening
- **Claim extraction:** modular clause decomposition (subordinate, relative, coordinated) with exact spans; hedging,
  hypotheticals, comparisons, units, version ranges, temporal markers and qualifiers. Unresolved-subject claims are
  kept and never verified. 26-case dataset.
- **Source authority:** trusted-domain registry, exact/subdomain matching, impersonation detection, entity matching,
  primary/secondary/unknown/suspicious tiers. Suspicious sources are never decisive.
- **Bugs fixed:**
  - pytest-style packages resolved the wrong import name (`_pytest`).
  - The AST cache served stale source after a package upgrade.
  - Empty model content was accepted.
  - Incomplete streams were accepted.
  - Invalid usage metadata crashed.
  - Non-numeric Tavily credits crashed.
  - The Docker base image was not created when a container ran directly on a fresh host (found by CI).
  - Root-owned Docker mount points broke repeated runs on non-root hosts (found by CI).
  - A NUL byte in a workspace path caused a 500 (fixed in 2.1.0).
- **Sandbox:**
  - Optional self-contained image mode (no host `/usr` mount).
  - Venv interpreter prefixes outside `/usr` (setup-python, pyenv) are mounted read-only.
  - IPC and nofile limits added; containers are force-removed on timeout.
- **Contract tests:** 31 provider and Tavily tests with fake transports (not live).
- **Offline demo suite:** `scripts/demo.sh offline`, with OK/UNEXPECTED checks.
- **Docs:** Windows/WSL2 setup, offline demo guide, problem-statement rationale with a placeholder for the official documents.
- **CI:** key-free GitHub Actions workflow (`.github/workflows/ci.yml`).

## Test results
- Backend: 228 passed, 2 skipped (live tests, no credentials). Same result with every task run inside Docker.
- Frontend: 9 passed, typecheck clean, production build OK.
- A fresh clone passes `scripts/setup.sh`, `scripts/test.sh` and `scripts/demo.sh offline`.
- GitHub Actions run 42352842174 is green: all three jobs passed.

## Still requires credentials (not claimed done)
Real Tavily retrieval, a real LLM provider, real evidence judging, an arbitrary task on a real model, and an
actual-token benchmark. Commands are in README → "After configuring API keys".

## Recommendation
After review, merge into `main`, then set **`main`** as the repository default branch (Settings → Default branch).
The default is currently the older `feat/vericode-main`.
