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

**What makes it different:**
- One principle for both tracks: **verify before you trust or generate**.
- The ground truth is the code **actually installed**, not model memory.
- The Track 2 verifiers double as Track 1 evidence.
- Token measurement never mixes provider-reported, estimated and mock numbers.

**Tech stack:** Python 3 · FastAPI · Pydantic v2 · SQLite · httpx · TypeScript compiler API (pinned TS 5.9.3) ·
React 19 + TypeScript + Tailwind v4 + Vite · Playwright · Docker sandbox · Tavily · Groq via the OpenAI-compatible
API (Anthropic adapter implemented, not live-tested) · GitHub Actions.

**Submission material:** [docs/submission/](docs/submission/): overview, Mermaid architecture and workflow
diagrams, track mapping, 5–7 minute demo script, results and limitations, checklist, labelled screenshots.

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

Full rationale: [docs/PROBLEM_STATEMENTS.md](docs/PROBLEM_STATEMENTS.md). Official sheets: [Track 1 PS1 (Tavily)](docs/problem-statements/track1-ps1.pdf),
[Track 2 PS1 (Bifrost)](docs/problem-statements/track2-ps1.pdf). Our selection, in our own words:
- **Track 1, PS1:** detect stale or incorrect information in LLM answers and verify it against evidence.
- **Track 2, PS1:** stop AI coding agents from using APIs that don't match the installed dependencies, while using fewer tokens.

Both are the same failure: a model trusting outdated knowledge. VeriCode applies one principle to both,
**verify before you trust or generate**, and shares the machinery. The installed-package verifiers built for
Track 2 also act as *version-specific evidence* for Track 1 claims about libraries (Demo E, "combined workflow").

## Status — what is implemented, tested, live-tested, mocked

Labels: **LOCAL** = implemented and locally tested · **CI** = passes key-free GitHub Actions CI · **LIVE** = verified
with actual Groq/Tavily requests ([report](docs/LIVE_VALIDATION.md)) · **MOCK** = mock/fake-transport tested only ·
**BLOCKED** = not yet verified. LIVE always means Groq `openai/gpt-oss-120b` through the OpenAI-compatible adapter
plus Tavily; **the Anthropic provider has never been live-tested** (no key).

| Capability | Status |
|---|---|
| Repository inspection (manifests, lockfiles, installed versions, conventions, relevant files, cache invalidation) | LOCAL · CI · LIVE (used by every live coding task) |
| Python API verification (static AST over installed pydantic 2.9.2: re-exports, inherited methods, deprecations, removed kwargs, positional values for `*args`) | LOCAL · CI · LIVE (pre-flight in live Python tasks; the `model_dump` false alarm is gone) |
| TypeScript verification via the compiler API (exports, namespace members, member paths, chained call results, `@deprecated`, call type-check) | LOCAL · CI · LIVE: the chained-call task resolved 8 chained APIs on a live plan (`z.string().trim().min`, `z.coerce.number().int().positive`, `expect().toThrow()`, …). The latest false-alarm fixes (`z.ZodSchema.parse`, module-prefixed names, task-named local identifiers) are LOCAL · CI only |
| Claim extraction (clause decomposition, spans, negation, hedging, hypotheticals, qualifiers) | LOCAL · CI · LIVE (Track 1 scenarios A-D). LLM-based extraction: MOCK |
| Source authority (exact/subdomain matching, impersonation, entity + product→publisher aliases, tiers) | LOCAL · CI · LIVE |
| Evidence sufficiency (weak sources never contradict, lexical never overrides stronger evidence, version monotonicity, undated pages can't override dated ones, negation-aware values) | LOCAL · CI · LIVE (scenario B → CONTRADICTED with correction 3.14; scenario D → UNVERIFIED; Demo E fixed) |
| LLM evidence judge with verbatim-quote validation | LOCAL · CI (fake transports) · LIVE (quotes verified; quote-less verdicts discarded) |
| Tavily search + extract, dates, retrieval timestamps, credits, persistence | LOCAL · CI (fake transports) · LIVE |
| OpenAI-compatible provider: text, structured output, streaming usage, truncation detection + bounded retry, error handling, rate-limit waits | LOCAL · CI · LIVE (Groq) |
| Anthropic provider | LOCAL · CI with fake transports only — **MOCK; never live-tested** |
| Coding agent on new, non-bundled tasks | LIVE: Python (pydantic v2) passed; TypeScript (zod) passed first try (3,026 tokens); chained-call TypeScript task passed first try (2,811 tokens); Demo C passed |
| Actual-token benchmark | LIVE for 3 tasks; savings computable for 2 (see [Measured results](#measured-results-honest)) |
| Docker sandbox (`--network none`, read-only rootfs, uid 65534, cap-drop ALL, limits, timeout kill) | CI (16 Docker tests on GitHub runners). Locally skipped here (no Docker daemon in this build environment) |
| Self-contained sandbox image (no host `/usr` mount) | LOCAL (command construction only); image build **BLOCKED** here (needs a registry pull) |
| Local auth (one-time token → HttpOnly session + CSRF, Host allowlist, loopback-only by default) | LOCAL · CI |
| Persisted settings + versioned SQLite migrations | LOCAL · CI |
| Confidence heatmap, 8-screen UI | LOCAL · CI (mock-provider browser tests: flows, 8 screens, mobile, empty states, error states, mock labelling, 9 tests) · LIVE (Playwright over persisted live results: 6/6 when the run has Track 1 data, 4 passed + 2 skipped otherwise) |
| Per-model cost (user-entered prices; never invented, never for MOCK) | LOCAL · CI |
| Historical MOCK benchmark numbers | MOCK (kept separate; never mixed with ACTUAL) |

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
Full report: [docs/LIVE_VALIDATION.md](docs/LIVE_VALIDATION.md). Everything marked LIVE in the status table ran against
real Groq and Tavily from GitHub Actions. Open items:
- The latest pre-flight false-alarm fixes are not yet exercised live.
- Anthropic has never been run live.

## Measured results (honest)

**Actual provider usage, current code** (Groq `openai/gpt-oss-120b`, 3 runs per mode, same model, repository snapshot,
repair budget (3) and acceptance tests). Mean ± stdev total tokens per run:

| Task | Success B / V | First pass B / V | Repairs B / V (mean) | Baseline tokens | VeriCode tokens | Savings |
|---|---|---|---|---|---|---|
| users (pydantic v1 APIs planned) | 3/3 / 3/3 | 0/3 / 2/3 | 2.3 / 0.3 | 10,635.7 ± 3,717.1 | 2,169 ± 725.1 | **79.6%** (pairs 76.6 / 73.6 / 85.6) |
| summary (no API risk) | 3/3 / 3/3 | 2/3 / 3/3 | 0.3 / 0 | 3,941.3 ± 1,842.6 | 1,987.7 ± 150.4 | **49.6%** (pairs 24.8 / 68.5 / 34.4) |
| signup (TypeScript zod, 3-file repo) | 3/3 / 3/3 | 3/3 / 3/3 | 0 / 0 | 767.3 ± 38.6 | 1,838.3 ± 65.6 | **−139.6%** (pairs −154.7 / −135.8 / −129.2): VeriCode costs more |

Runs: users [42448014676](https://github.com/Clint0-0/VeriCode/actions/runs/42448014676); summary
[42461511457](https://github.com/Clint0-0/VeriCode/actions/runs/42461511457); signup [42491474776](https://github.com/Clint0-0/VeriCode/actions/runs/42491474776) (fresh 3 + 3 on `38ff1f5`).

**Reading:** VeriCode saved tokens where the baseline needed repairs. Each baseline repair resends the whole
repository; VeriCode's planner + pre-flight cost about 550-730 tokens and avoided those repairs. On the tiny `signup`
task the baseline succeeded first try with about 760 tokens, so VeriCode's planner + pre-flight overhead (about 920 tokens) makes it about 2.4x more expensive. **These
are three small demo tasks. They are not a general savings claim.**

**Earlier actual run, before the planner optimisation and pre-flight fixes (run 42397432837, superseded):**

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
- Actual-token savings are measured on three small demo tasks, computable for two (79.6%, 49.6%). On the smallest task
  VeriCode costs about 2.3x the baseline. There is no general savings claim.
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

## Future work
- Benchmark larger, more diverse repositories, where avoided repairs should matter more.
- More package ecosystems (Go, Rust, Java), stronger semantic claim verification, more evidence providers.
- Skip the planner for tasks that touch no third-party API (the main overhead on tiny tasks).
- Live-test the Anthropic provider and one more OpenAI-compatible model.
- Build and publish the self-contained sandbox image.

