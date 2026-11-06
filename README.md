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
scripts/demo.sh all     # Demo 1 (Python), 1b (TypeScript), 2 (stale answers), 3 (benchmark)
```

If the Docker daemon is running, test commands execute in a container. Otherwise they run in the labelled
process sandbox (`VERICODE_SANDBOX=auto|docker|process`).

## Status — what is implemented, tested, live-tested, mocked

| Capability | Status |
|---|---|
| Repository inspection (manifests, lockfiles, installed versions, conventions, relevant files, cache invalidation) | Implemented and tested |
| Python API verification (static AST: re-exports, `_dynamic_imports`, inherited methods, `@deprecated`, `warnings.warn`, removed kwargs, migration messages) | Implemented and tested against real pydantic 2.9.2 |
| TypeScript verification via the compiler API (module resolution, exports, members, signatures, generics, `@deprecated`, call type-check) | Implemented and tested against real zod 3.23.8 |
| Claim extraction: compound splitting with spans, negation, conditionals, opinions, date ranges | Implemented and tested (deterministic). LLM extraction implemented; mocked-HTTP tests only |
| Semantic verification: lexical + negation | Implemented and tested |
| LLM evidence judge (quotes must appear verbatim in the source) | Implemented; mocked-HTTP tests only, **not live-tested** |
| Tavily search + extract (aligned with the current OpenAPI spec: `include_published_date`, `include_usage`, `include_domains_mode`, 432/433 quota codes) | Implemented; mocked-HTTP tests. **Not live-tested**: no key, and `api.tavily.com` is blocked by this build environment's egress proxy |
| Anthropic + OpenAI providers, structured outputs, retries, timeouts, provider-reported usage | Implemented; mocked-HTTP tests. **Not live-tested** (no key) |
| Coding agent on arbitrary tasks (real provider) | Implemented. Only the scripted mock has been run here (3 bundled tasks) |
| Docker sandbox (`--network none`, read-only rootfs, uid 65534, cap-drop ALL, memory/CPU/pids limits, timeout kill) | Implemented and tested (isolation probes run inside the container) |
| Local auth: token → HttpOnly SameSite=Strict session + CSRF, Host-header allowlist, refuses non-loopback bind without opt-in | Implemented and tested |
| Persisted settings + versioned SQLite migrations | Implemented and tested (restart simulation) |
| Benchmarks: separate measurement classes, paired savings, savings only for comparable successes | Implemented and tested. **All recorded numbers are MOCK** |

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
