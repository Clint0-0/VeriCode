# VeriCode — Verify Before You Generate

VeriCode is a verification layer that sits between an AI and what it is about to rely on. It covers two
hackathon problem statements in one product.

**Track 1 — Stale-Answer Detector.** Paste any LLM answer. VeriCode:
- splits it into atomic claims, each traceable to a character span of the original text;
- classifies each claim by category, volatility, temporal sensitivity, verifiability and the evidence type it needs;
- searches **Tavily** only for time-sensitive claims and inspects the retrieved page content;
- decides each status with value checks, lexical/negation checks and, when a real LLM is configured, a
  quote-validated LLM evidence judge;
- reports `CURRENT_SUPPORTED`, `POTENTIALLY_STALE`, `CONTRADICTED`, `UNVERIFIED`, `CONFLICTING_EVIDENCE` or `NOT_APPLICABLE`;
- gives **evidence freshness** and **verification confidence** as two separate scores, shows supporting and
  contradicting sources side by side, and writes a cited corrected answer that never invents a fix.

**Track 2 — Pre-Flight API & Dependency Gatekeeper + token-efficient coding agent.** Before any code is generated:
1. A planner lists the third-party APIs it intends to call.
2. VeriCode checks every planned import, class, method and argument against the code **actually installed** in the
   repository. Python is checked by static AST analysis of site-packages. TypeScript/JavaScript is checked with the
   **TypeScript compiler API** against node_modules: export maps, named and default exports, signatures, generics,
   `@deprecated`, and a real type-check of the planned call.
3. Tavily documentation is used only when the local check isn't enough.
4. The coder receives a compact briefing with only the needed corrections, plus the relevant files and the project's conventions.
5. Changes are applied in a sandbox copy (Docker, no network), tests, typecheck and lint run there, and failures are
   repaired within a fixed budget.
6. Every token is counted and labelled `ACTUAL_PROVIDER_USAGE`, `ESTIMATED` or `MOCK`.

## Quick start

```bash
scripts/setup.sh        # venvs, demo projects (pydantic 2.9.2, zod 3.23.8), TypeScript checker, frontend build, .env
$EDITOR .env            # TAVILY_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY, VERICODE_CODER_MODEL (+ optional VERICODE_PLANNER_MODEL)
scripts/run.sh          # http://127.0.0.1:8000 — open the login URL it prints (token also in .vericode_token)
scripts/test.sh         # backend + frontend tests
scripts/demo.sh all     # A Python compat · B TypeScript compat · D stale answer · E combined · C arbitrary task · 3 benchmark
```

No keys yet? `scripts/demo.sh offline` runs every key-free demo with an OK/UNEXPECTED check
([docs/OFFLINE_DEMO.md](docs/OFFLINE_DEMO.md)). **Windows:** use WSL2 ([docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md)).

If the Docker daemon is running, test commands execute in a container. Otherwise they run in the labelled
process sandbox (`VERICODE_SANDBOX=auto|docker|process`).

## The two problem statements and why they are combined

Full rationale: [docs/PROBLEM_STATEMENTS.md](docs/PROBLEM_STATEMENTS.md). The official problem-statement documents
were **not available**, so this README doesn't quote them; add them to `docs/problem-statements/`. Our selection, in our own words:
- **Track 1, PS1:** detect stale or incorrect information in LLM answers and verify it against evidence.
- **Track 2, PS1:** stop AI coding agents from using APIs that don't match the installed dependencies, while using fewer tokens.

Both are the same failure: a model trusting outdated knowledge. VeriCode applies one principle to both,
**verify before you trust or generate**, and shares the machinery. The installed-package verifiers built for
Track 2 also act as *version-specific evidence* for Track 1 claims about libraries (Demo E, "combined workflow").

## Status — what is implemented, tested, live-tested, mocked

| Capability | Status |
|---|---|
| Repository inspection (manifests, lockfiles, installed versions, conventions, relevant files, cache invalidation) | Implemented and tested |
| Python API verification (static AST: re-exports, `_dynamic_imports`, inherited methods, `@deprecated`, `warnings.warn`, removed kwargs, migration messages) | Implemented and tested against real pydantic 2.9.2 |
| TypeScript verification via the compiler API (module resolution, exports, members, signatures, generics, `@deprecated`, call type-check) | Implemented and tested against real zod 3.23.8 |
| Claim extraction: modular clause decomposition (subordinate, relative, coordinated) with exact spans; negation, conditionals, hedging, hypotheticals, opinions, comparisons, units, version ranges, temporal markers, qualifiers, unresolved-subject handling | Implemented and tested (26-case deterministic dataset). LLM extraction implemented; mocked-HTTP tests only |
| Source authority registry: exact/subdomain matching, impersonation detection, entity matching, primary/secondary/unknown/suspicious tiers | Implemented and tested (offline fixtures incl. impersonation and unrelated official sources) |
| Semantic verification: lexical + negation | Implemented and tested |
| LLM evidence judge (quotes must appear verbatim in the source) | Implemented; mocked-HTTP tests only, **not live-tested** |
| Provider and Tavily **contract tests** (malformed/empty/missing fields, invalid usage, incomplete streams, 401/429/5xx, timeouts, retry exhaustion, provider switching) | Implemented and tested with fake transports. These are **not** live tests |
| Tavily search + extract (aligned with the current OpenAPI spec: `include_published_date`, `include_usage`, `include_domains_mode`, 432/433 quota codes) | Implemented; mocked-HTTP tests. **Not live-tested**: no key, and `api.tavily.com` is blocked by this build environment's egress proxy |
| Anthropic + OpenAI providers, structured outputs, retries, timeouts, provider-reported usage | Implemented; mocked-HTTP tests. **Not live-tested** (no key) |
| Coding agent on arbitrary tasks (real provider) | Implemented. Only the scripted mock has been run here (3 bundled tasks) |
| Docker sandbox (`--network none`, read-only rootfs, uid 65534, cap-drop ALL, memory/CPU/pids limits, timeout kill) | Implemented and tested (isolation probes, fork bomb, host-file and symlink escape, read-only dependency dirs, TypeScript check in container, cleanup) |
| Self-contained sandbox image (no host `/usr` mount) | Implemented. Command construction tested; image **build not executed here** (needs a registry pull) |
| GitHub Actions CI (key-free) | Implemented and **passing on GitHub**: backend 222 + 16 Docker-sandbox tests, offline demo suite, frontend typecheck/tests/build, 6 browser e2e |
| Local auth: token → HttpOnly SameSite=Strict session + CSRF, Host-header allowlist, refuses non-loopback bind without opt-in | Implemented and tested |
| Persisted settings + versioned SQLite migrations | Implemented and tested (restart simulation) |
| Benchmarks: separate measurement classes, paired savings, savings only for comparable successes, flagged-API usage shipped by each mode | Implemented and tested. **All recorded numbers are MOCK** |
| Combined workflow: Track 1 API claims checked against installed packages (Python AST / TS compiler) | Implemented and tested (real pydantic 2.9.2 / zod 3.23.8) |
| Confidence heatmap (per library × planned API, colours = verification status, plus "auto-corrected" from the final diff) | Implemented and tested (UI + e2e) |
| Provider streaming (Anthropic SSE, OpenAI `stream_options.include_usage`) for coder/repair, with usage from stream events | Implemented; mocked-HTTP tests only, **not live-tested** |
| Per-model cost (user-entered prices; never invented, never for MOCK) | Implemented and tested |
| Browser end-to-end tests (real server + Chromium): login, Track 1, combined, pre-flight heatmap, coding task, all 8 screens, mobile | Implemented and passing |

## After configuring API keys (exact commands)
```bash
# in .env: TAVILY_API_KEY=...  ANTHROPIC_API_KEY=... (or OPENAI_API_KEY=...)  VERICODE_CODER_MODEL=<model id>  [VERICODE_PLANNER_MODEL=<model id>]
VERICODE_LIVE_TESTS=1 .venv/bin/python -m pytest -q -p no:cacheprovider backend/tests -m live -rs   # live Tavily + real planner/coder
scripts/demo.sh d --live          # Track 1 with live Tavily retrieval (+ LLM evidence judge if an LLM key is set)
scripts/demo.sh c                 # arbitrary coding task with the real model (baseline and VeriCode)
scripts/demo.sh 3 --runs 3        # ACTUAL_PROVIDER_USAGE benchmark (3 runs per mode)
```

## Blockers for full live validation (require user action)

| Blocker | Action |
|---|---|
| No `TAVILY_API_KEY`; `api.tavily.com` refused by this build environment's egress proxy | Add the key to `.env`, run where Tavily is reachable (or allow the domain), then `VERICODE_LIVE_TESTS=1 .venv/bin/python -m pytest backend/tests -m live` |
| No LLM key (`api.openai.com` also blocked here; `api.anthropic.com` reachable) | Set `ANTHROPIC_API_KEY` (or OpenAI) + `VERICODE_CODER_MODEL`, then `scripts/demo.sh c` and `scripts/demo.sh 3 --runs 3` |

Until then, **these Definition-of-Done items are not met:** real Tavily retrieval, a real LLM provider, real
evidence judging, an arbitrary task run on a real model, and actual-token benchmark results.

## Measured results (honest)

Real-provider numbers: **none yet** (no LLM key available while this was built). The only benchmark that has run
used the **scripted mock provider (MOCK, chars/4)**. It demonstrates the mechanics, not real-model efficiency:

| Task | Baseline | VeriCode | Savings | First pass (B/V) | Final success (B/V) |
|---|---|---|---|---|---|
| Demo 1 users (pydantic v1 APIs planned) | 11,779 | 1,421 | 87.9% | 0% / 100% | 100% / 100% |
| Demo 3 priority_summary (no API risk) | 2,495 | 1,466 | 41.2% | 100% / 100% | 100% / 100% |
| Demo 1b zod signup (TS, 3-file repo) | 1,231 | 1,415 | **−14.9%** | 0% / 100% | 100% / 100% |

The negative row is kept on purpose. On a tiny repository the planner overhead (607 tokens) costs more than the
context it saves. In that run the baseline also shipped the deprecated `nonempty()` call, which tests don't catch.
With real credentials, run `scripts/demo.sh 3 --runs 3` to get `ACTUAL_PROVIDER_USAGE` results. The dashboard keeps
mock and real benchmarks apart.

## Required environment variables

| Variable | Needed for |
|---|---|
| `TAVILY_API_KEY` | live evidence (Track 1, API docs fallback) |
| `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (+ `OPENAI_BASE_URL` for compatible gateways) | real planner, coder, judge |
| `VERICODE_CODER_MODEL` (and optionally `VERICODE_PLANNER_MODEL`) | model ids, never hardcoded |
| `VERICODE_LLM_PROVIDER=mock` | explicit offline demo mode (chosen automatically when no key is set and `VERICODE_DEMO_MODE=1`) |
| `VERICODE_SANDBOX`, `VERICODE_SANDBOX_MEMORY`, `VERICODE_SANDBOX_CPUS` | execution isolation |
| `VERICODE_AUTH_TOKEN` (optional fixed token), `VERICODE_HOST`, `VERICODE_ALLOW_REMOTE` | access control |

A configured real provider that fails returns an error. It never falls back to mock.

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Security](docs/SECURITY.md) ·
[Benchmark method](docs/BENCHMARK.md) · [Demo guide](docs/DEMO.md) · [Setup & testing](docs/SETUP.md) · [Changelog](CHANGELOG.md)

## Known limitations

- No live Tavily or LLM run has been performed (credentials unavailable, and Tavily/OpenAI hosts are blocked by the
  build sandbox). Live tests exist: `VERICODE_LIVE_TESTS=1 scripts/test.sh -m live`.
- The deterministic claim splitter handles common English structures. Complex rhetoric needs the optional LLM
  extraction, which requires a real provider. Lexical support is weaker than value or judge evidence and is penalised in confidence.
- Source authority comes from configurable rules plus heuristics: domain classes, and the claim's entity matching
  the domain. It cannot by itself prove that a page is official.
- The Docker sandbox mounts the host `/usr` read-only to avoid image pulls. Interpreters must live under `/usr`
  (or `node` under its own prefix, which is mounted read-only automatically).
- Single-user local tool: one access token, no user accounts or roles.
- Mock coding supports only the 3 bundled tasks. Real-provider mode accepts any task.
