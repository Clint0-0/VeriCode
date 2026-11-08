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
| LLM evidence judge (quotes must appear verbatim in the source) | **Live-tested** with Groq `openai/gpt-oss-120b`: verbatim quotes accepted, quote-less verdicts discarded ([report](docs/LIVE_VALIDATION.md)) |
| Provider and Tavily **contract tests** (malformed/empty/missing fields, invalid usage, incomplete streams, 401/429/5xx, timeouts, retry exhaustion, provider switching) | Implemented and tested with fake transports. These are **not** live tests |
| Tavily search + extract (aligned with the current OpenAPI spec: `include_published_date`, `include_usage`, `include_domains_mode`, 432/433 quota codes) | **Live-tested** in GitHub Actions: search, extract, dates, retrieval timestamps, credits, persistence |
| Anthropic + OpenAI-compatible providers, structured outputs, retries, timeouts, provider-reported usage | OpenAI-compatible path **live-tested with Groq** (text, structured planner, skeleton, streaming, usage, errors). Anthropic: mocked-HTTP only (no key). Output truncation (`finish_reason=length`) and 429 are handled explicitly |
| Coding agent on arbitrary tasks (real provider) | **Live with Groq**: new Python task and Demo C passed first try; new TypeScript task failed on planner truncation (fixed, not yet re-confirmed live) |
| Docker sandbox (`--network none`, read-only rootfs, uid 65534, cap-drop ALL, memory/CPU/pids limits, timeout kill) | Implemented and tested (isolation probes, fork bomb, host-file and symlink escape, read-only dependency dirs, TypeScript check in container, cleanup) |
| Self-contained sandbox image (no host `/usr` mount) | Implemented. Command construction tested; image **build not executed here** (needs a registry pull) |
| GitHub Actions CI (key-free) | Implemented and **passing on GitHub**: backend 222 + 16 Docker-sandbox tests, offline demo suite, frontend typecheck/tests/build, 6 browser e2e |
| Local auth: token → HttpOnly SameSite=Strict session + CSRF, Host-header allowlist, refuses non-loopback bind without opt-in | Implemented and tested |
| Persisted settings + versioned SQLite migrations | Implemented and tested (restart simulation) |
| Benchmarks: separate measurement classes, paired savings, savings only for comparable successes, flagged-API usage shipped by each mode | Implemented and tested. One **ACTUAL_PROVIDER_USAGE** run on Groq (see below); historical MOCK numbers kept separately |
| Combined workflow: Track 1 API claims checked against installed packages (Python AST / TS compiler) | Implemented and tested (real pydantic 2.9.2 / zod 3.23.8) |
| Confidence heatmap (per library × planned API, colours = verification status, plus "auto-corrected" from the final diff) | Implemented and tested (UI + e2e) |
| Provider streaming (Anthropic SSE, OpenAI `stream_options.include_usage`) for coder/repair, with usage from stream events | OpenAI-compatible streaming **live-tested on Groq**: usage arrives in the stream (ACTUAL, not ESTIMATED) |
| Per-model cost (user-entered prices; never invented, never for MOCK) | Implemented and tested |
| Browser end-to-end tests (real server + Chromium): login, Track 1, combined, pre-flight heatmap, coding task, all 8 screens, mobile | Implemented and passing |

## Live configuration (Groq + Tavily, no Anthropic key needed)
Groq runs through the existing OpenAI-compatible adapter. In `.env` (gitignored, never commit it):
```bash
TAVILY_API_KEY=...                                   # https://app.tavily.com
VERICODE_LLM_PROVIDER=openai
OPENAI_API_KEY=...                                   # Groq key from https://console.groq.com/keys
OPENAI_BASE_URL=https://api.groq.com/openai/v1
VERICODE_CODER_MODEL=openai/gpt-oss-120b             # any chat model id listed for your Groq account
VERICODE_PLANNER_MODEL=openai/gpt-oss-120b
VERICODE_DEMO_MODE=0
# VERICODE_STRUCTURED_REASONING_EFFORT=low           # optional; planner/judge/extraction only (dropped if rejected)
# VERICODE_REASONING_EFFORT=low                      # optional; all stages
```
Commands:
```bash
cd backend && ../.venv/bin/python -m vericode.live_validation --runs 3   # full live harness -> reports/live/
VERICODE_LIVE_TESTS=1 .venv/bin/python -m pytest -q -p no:cacheprovider backend/tests -m live -rs
scripts/demo.sh d --live          # Track 1 with live Tavily + Groq evidence judge
scripts/demo.sh c                 # arbitrary coding task, baseline and VeriCode
scripts/demo.sh 3 --runs 3        # ACTUAL_PROVIDER_USAGE benchmark
```
In GitHub: put the two keys in **Secrets** and the other four values in **Variables** (Settings -> Secrets and
variables -> Actions), then Actions -> "Live validation (manual, uses API credits)" -> Run workflow. It is manual so
it never spends credits on a push. Use `only=` to run selected harness sections.

## Live validation status
Full report: [docs/LIVE_VALIDATION.md](docs/LIVE_VALIDATION.md). Confirmed against real Groq (`openai/gpt-oss-120b`)
and Tavily:
- provider config, text, structured planner, skeleton, streaming usage, error handling, truncation detection and
  bounded retry, and the evidence judge with verbatim quotes;
- Tavily search and extract;
- Track 1 scenarios A-D: an outdated "latest version" claim is now CONTRADICTED, and weak-source contradictions are
  now UNVERIFIED;
- Demo E (installed code + Tavily);
- new Python and TypeScript coding tasks, and Demo C;
- a browser pass over persisted live results (6/6).

Still open: the actual-token benchmark for 2 of 3 tasks, and live confirmation of the last pre-flight fixes. Both are
blocked by Groq rate limits.

## Measured results (honest)

**Actual provider usage, optimised code (Groq `openai/gpt-oss-120b`, 3 runs per mode, run 42448014676):**

| Task | Success (B/V) | First pass (B/V) | Baseline tokens | VeriCode tokens | Savings |
|---|---|---|---|---|---|
| users (pydantic v1 APIs planned) | 3/3 / 3/3 | 0/3 / 2/3 | 10,635.7 ± 3,717.1 | 2,169 ± 725.1 | **79.6%** (paired 76.6 / 73.6 / 85.6) |
| summary, signup | blocked by Groq HTTP 429 | | | | not measured |

The saving comes from avoided repairs: the baseline averaged 2.3 repairs, each resending the whole repository.
VeriCode averaged 0.3, at 733 tokens of planning overhead. That is one task with n=3; no TypeScript savings figure
exists for the optimised code.

**Earlier actual run, pre-optimisation code (run 42397432837):**

| Task | Success (B/V) | Baseline tokens | VeriCode tokens | Savings |
|---|---|---|---|---|
| users | 33% / 100% | 5,449.7 | 4,316.3 | not computed (baseline failures) |
| summary | 67% / 100% | 2,874 | 2,713.3 | not computed (baseline failure) |
| signup (TypeScript zod) | 100% / 100% | 776.7 | 2,721 | **-250.3%** |

**Historical MOCK benchmark (scripted provider, chars/4 - mechanics only, not comparable with the table above):**

| Task | Baseline | VeriCode | Savings | First pass (B/V) | Final success (B/V) |
|---|---|---|---|---|---|
| Demo 1 users (pydantic v1 APIs planned) | 11,779 | 1,421 | 87.9% | 0% / 100% | 100% / 100% |
| Demo 3 priority_summary (no API risk) | 2,495 | 1,466 | 41.2% | 100% / 100% | 100% / 100% |
| Demo 1b zod signup (TS, 3-file repo) | 1,231 | 1,415 | **−14.9%** | 0% / 100% | 100% / 100% |

The negative row is kept on purpose. On a tiny repository the planner overhead (607 tokens) costs more than the
context it saves. In that run the baseline also shipped the deprecated `nonempty()` call, which tests don't catch.
The dashboard keeps mock and real benchmarks apart.

## Required environment variables

| Variable | Needed for |
|---|---|
| `TAVILY_API_KEY` | live evidence (Track 1, API docs fallback) |
| `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` (+ `OPENAI_BASE_URL` for compatible gateways such as Groq) | real planner, coder, judge |
| `VERICODE_REASONING_EFFORT` (optional) | sent as `reasoning_effort` to OpenAI-compatible endpoints only when set |
| `VERICODE_CODER_MODEL` (and optionally `VERICODE_PLANNER_MODEL`) | model ids, never hardcoded |
| `VERICODE_LLM_PROVIDER=mock` | explicit offline demo mode (chosen automatically when no key is set and `VERICODE_DEMO_MODE=1`) |
| `VERICODE_SANDBOX`, `VERICODE_SANDBOX_MEMORY`, `VERICODE_SANDBOX_CPUS` | execution isolation |
| `VERICODE_AUTH_TOKEN` (optional fixed token), `VERICODE_HOST`, `VERICODE_ALLOW_REMOTE` | access control |

A configured real provider that fails returns an error. It never falls back to mock.

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [Security](docs/SECURITY.md) ·
[Benchmark method](docs/BENCHMARK.md) · [Live validation](docs/LIVE_VALIDATION.md) · [Demo guide](docs/DEMO.md) · [Setup & testing](docs/SETUP.md) · [Changelog](CHANGELOG.md)

## Known limitations

- Live runs so far: Groq (`openai/gpt-oss-120b`) + Tavily in GitHub Actions only; Anthropic never live-tested.
  Groq free-tier rate limits (HTTP 429) cut the last validation run short.
- Actual-token savings are measured on one task only (79.6%, n=3). On the old code the small TypeScript task cost
  3.5x more with VeriCode, and it has not been re-measured since the planner optimisation.
- Low-authority sources may still *support* a claim (noted in the explanation, low confidence); they can no longer
  contradict one.
- Groq free-tier limits (8,000 tokens/min plus a longer cap) make full benchmarks slow or blocked; the client waits
  out short resets and stops on long ones.
- The sentence splitter treats a sentence that starts with a lowercase word (e.g. "zod provides ...") as part of
  the previous sentence.
- The deterministic claim splitter handles common English structures. Complex rhetoric needs the optional LLM
  extraction, which requires a real provider. Lexical support is weaker than value or judge evidence and is penalised in confidence.
- Source authority comes from configurable rules plus heuristics: domain classes, and the claim's entity matching
  the domain. It cannot by itself prove that a page is official.
- The Docker sandbox mounts the host `/usr` read-only to avoid image pulls. Interpreters must live under `/usr`
  (or `node` under its own prefix, which is mounted read-only automatically).
- Single-user local tool: one access token, no user accounts or roles.
- Mock coding supports only the 3 bundled tasks. Real-provider mode accepts any task.
