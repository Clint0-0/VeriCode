# VeriCode — Verify Before You Generate

VeriCode checks what an AI is about to rely on before it relies on it.

1. **Stale-Answer Detector (Track 1).** Paste any LLM answer. VeriCode splits it into individual claims and
   works out which ones can go out of date (versions, prices, laws, leadership, deadlines…). It checks those
   claims against Tavily live search and any URLs you supply, then labels each claim *supported*,
   *potentially stale*, *contradicted*, *conflicting* or *unverified*. Every label comes with its sources.
   Two separate scores are reported: evidence freshness and verification confidence.
2. **Token-efficient coding agent (Track 2).** Before writing any code, a planner lists the third-party APIs
   it intends to call. VeriCode checks each one against the package source **actually installed** in the
   project (AST of site-packages / `.d.ts` in node_modules), and uses Tavily when the local check isn't enough.
   It then gives the coder a compact *pre-flight briefing* plus only the relevant files. Code is generated,
   applied in a sandbox copy, tested and repaired within a fixed budget, and every token is counted.

> **Local-first verification + live source validation + minimal context injection + real execution + measured tokens.**

## Quick start

```bash
scripts/setup.sh                # backend venv, demo project venv (pydantic 2.9.2), frontend build, .env
$EDITOR .env                    # add TAVILY_API_KEY and ANTHROPIC_API_KEY or OPENAI_API_KEY + model ids
scripts/run.sh                  # API + dashboard on http://127.0.0.1:8000
scripts/test.sh                 # backend pytest + frontend typecheck/vitest
scripts/demo.sh all             # the three hackathon demos in the terminal
```

Frontend development with hot reload: `cd frontend && npm run dev` (port 5173, proxies `/api` to :8000).

### What runs without credentials

| Capability | No keys | `TAVILY_API_KEY` | LLM key + `VERICODE_CODER_MODEL` |
|---|---|---|---|
| Repository inspection, dependency truth, API verification (deterministic) | ✅ | ✅ | ✅ |
| Stale-answer detection | offline **fixture** mode, or live mode reporting `UNVERIFIED (missing_key)` | ✅ live | ✅ |
| Live documentation evidence for API findings | reported as "not performed" | ✅ | ✅ |
| Coding agent / benchmark | **scripted mock provider**: only the 2 bundled demo tasks, token counts *estimated* | same | ✅ real generation, provider-reported tokens |

The mock provider is labelled everywhere it appears (sidebar, dashboard, task reports, benchmark
`measurement` field). It does not reason. It returns canned code that behaves the way a model with
Pydantic-v1 knowledge would: it writes v1-style APIs unless the prompt contains the corrected API, which
can come from a VeriCode briefing or from a test-failure message. Any other task fails explicitly with
`MOCK_PROVIDER_NO_SCRIPT`.

## The three demos

See [docs/DEMO.md](docs/DEMO.md). In short:

- **Demo 1 – Pre-flight API detection.** `demos/sample_project` declares `pydantic>=1.10` but has
  pydantic **2.9.2** installed. The planner proposes `Field(regex=…)`, `@validator` and `.dict()`.
  VeriCode finds the problems in the installed source:
  - `Field(regex=)` → **INCOMPATIBLE** (`fields.py:685` raises "`regex` is removed. use `pattern`").
  - `validator` → **DEPRECATED** (decorated `@deprecated`, points to `field_validator`).
  - `BaseModel.dict` → **DEPRECATED** (points to `model_dump`).

  The briefing goes to the coder, and the acceptance tests (deprecations treated as errors) pass on the
  first attempt.
- **Demo 2 – Stale-answer detection.** A 4-claim answer gives one contradicted claim (Python 3.12 is
  "latest"), one supported claim (3.14 introduced t-strings), one unverified claim and one stable fact. You
  get evidence links, freshness, confidence and a cited corrected answer. Fixture mode is offline and
  labelled; `--live` uses Tavily.
- **Demo 3 – Baseline vs VeriCode.** Same tasks, provider, repository copy, tests and repair budget.
  Savings are counted only when both modes succeed.

## Results we actually measured (this environment)

No LLM or Tavily key was available while this was built, so the numbers below come from the **scripted mock
provider with estimated tokens (chars/4)**. They show that the pipeline works and how large the context
difference is. They are **not** evidence of real-model savings. With a real key, run
`scripts/demo.sh 3 --runs 3` to get provider-reported numbers.

| Task | Baseline tokens | VeriCode tokens | Savings | First-pass (B/V) | Final success (B/V) | Repairs (B/V) |
|---|---|---|---|---|---|---|
| Demo 1 users (incompatible API) | 11,779 | 1,302 | 88.9% | 0% / 100% | 100% / 100% | 3 / 0 |
| Demo 3 priority_summary (no API risk) | 2,495 | 1,346 | 46.1% | 100% / 100% | 100% / 100% | 0 / 0 |

n = 3 runs per mode, sd = 0. Mock outputs are deterministic, so the spread will only appear with real models.
Detection on Demo 1: 3/3 problematic APIs flagged and 0/1 false positives (BaseModel is reported `STALE`
because it exists but the plan assumed v1; that is not counted as a problem).

## Documentation

- [Architecture](docs/ARCHITECTURE.md): modules, data flow, scoring formulas
- [API reference](docs/API.md): every implemented endpoint
- [Security](docs/SECURITY.md): what is and isn't isolated
- [Benchmark methodology](docs/BENCHMARK.md)
- [Demo guide](docs/DEMO.md)
- [Setup, running and testing](docs/SETUP.md)

## Known limitations

- **No real-model benchmark yet.** Real token savings and success rates have not been measured; that needs credentials.
- **Live Tavily calls have not been made from this environment** (no key). The client follows the documented REST
  contract (`POST https://api.tavily.com/search` and `/extract`, Bearer auth) and is tested against mocked
  transports covering success, missing key, timeout, 429, invalid schema and no results.
- **Claim verification is deterministic and value-based.** It compares versions, prices, names, percentages
  and years. Claims with no concrete value (e.g. "X supports streaming") end up `UNVERIFIED` rather than
  being guessed. Sentence-level claim splitting is heuristic.
- **Source authority comes from domain heuristics** (government, docs/org, registry, news, community).
  A company's own `.com` site counts as general web unless it is listed in *preferred domains*.
- **JS/TS checks read export maps and `.d.ts` files.** Argument checks for TS are name-based and therefore
  weak. The TS-compiler check only runs when the project has `typescript` installed.
- **Python checks are static** (decorators `@deprecated`, top-level `warnings.warn`, `kwargs.pop(...)`+`raise`
  rejection patterns, re-exports including `_dynamic_imports`, base classes in the same package). Behaviour
  that only shows up at runtime may be missed; findings are then reported as `VERIFIED_LOCAL` with medium
  confidence, or `UNCERTAIN`.
- **The sandbox is process-level, not a container**: rlimits, scrubbed env, allowlisted argv, timeout, no network
  via `unshare -rn` when the kernel allows it (it did here). Tests run on the host filesystem inside a copy of
  the workspace. See SECURITY.md.
- **Settings edited in the UI are runtime-only.** Persist them in `.env`.
