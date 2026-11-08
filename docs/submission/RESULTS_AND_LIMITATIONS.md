# Results and limitations

All numbers come from recorded runs. Labels: **LOCAL**, **CI**, **LIVE** (real Groq `openai/gpt-oss-120b` through the
OpenAI-compatible API + Tavily, run in GitHub Actions), **MOCK**, **BLOCKED**. Full run log:
[../LIVE_VALIDATION.md](../LIVE_VALIDATION.md).

## Live validation summary

| Area | Result | Label |
|---|---|---|
| Groq: text, structured planner, API skeleton, streaming usage, truncation detection + bounded retry, error handling, rate-limit handling, quota tracking | all succeeded | LIVE |
| Evidence judge: structured verdict with verbatim quotes; quote-less verdict discarded | succeeded | LIVE |
| Tavily: search, extract, URLs, published dates, retrieval timestamps, credits, persistence | succeeded | LIVE |
| Track 1 scenario A (current facts) | CURRENT_SUPPORTED | LIVE |
| Track 1 scenario B (outdated "latest Python 3.10") | CONTRADICTED, correction 3.14 | LIVE |
| Track 1 scenario C (semantic claims) | supported via judge; a quote-less judge verdict correctly discarded | LIVE |
| Track 1 scenario D (forward-looking, weak sources) | UNVERIFIED (weak sources can't contradict) | LIVE |
| Demo E (installed code + Tavily) | `@validator` CONTRADICTED by installed pydantic; `model_dump()` CURRENT_SUPPORTED | LIVE |
| New Python task (pydantic v2) | passed | LIVE |
| New TypeScript task (zod) | passed first try, 3,026 tokens, 7/7 APIs verified | LIVE |
| **Chained-call TypeScript task** | passed first try, 2,811 tokens; **8 chained APIs resolved through call return types** (`z.string().trim().min`, `z.coerce.number().int().positive`, `z.array().default`, `expect().toThrow()`, …) | LIVE (run 42465099749) |
| Demo C (arbitrary task) | passed | LIVE |
| Browser over persisted live results | 6/6 with Track 1 data; 4 passed + 2 skipped in runs without Track 1 data | LIVE |
| Browser, mock provider (flows, 8 screens, mobile, empty/error states, mock labelling) | 9/9 | CI |
| Anthropic provider | never run live (no key) | MOCK |

## Actual-token benchmark (3 runs per mode, same model, snapshot, repair budget 3, acceptance tests)

| Task | Success B / V | First pass B / V | Repairs B / V | Baseline tokens (mean ± sd) | VeriCode tokens (mean ± sd) | Savings |
|---|---|---|---|---|---|---|
| users | 3/3 / 3/3 | 0/3 / 2/3 | 2.3 / 0.3 | 10,635.7 ± 3,717.1 | 2,169 ± 725.1 | **79.6%** (pairs 76.6 / 73.6 / 85.6) |
| summary | 3/3 / 3/3 | 2/3 / 3/3 | 0.3 / 0 | 3,941.3 ± 1,842.6 | 1,987.7 ± 150.4 | **49.6%** (pairs 24.8 / 68.5 / 34.4) |
| signup | 3/3 / 3/3 | 3/3 / 3/3 | 0 / 0 | 767.3 ± 38.6 | 1,838.3 ± 65.6 | **−139.6%** (pairs −154.7 / −135.8 / −129.2): VeriCode costs more |

`signup`: fresh 3 + 3 set on `38ff1f5` (run 42491474776), no rate limits. Both modes passed first try; VeriCode's
planner + pre-flight overhead (about 920 tokens) bought nothing because the baseline needed no repairs. Earlier attempts
(42461511457, 42462137064, 42465099749, 42465458363) were blocked by Groq 429. **VeriCode saves tokens when the baseline
would need repairs, and costs more on tiny tasks that pass first try.**

Tavily usage is counted separately from tokens: 1 search in one `users` VeriCode run; none in `summary` or `signup`.
The coding pipeline makes no evidence-judge call, so judge tokens are 0 in these benchmarks.

**Interpretation.** Savings came from avoided repairs: each baseline repair resends the whole repository. VeriCode's
planner and pre-flight cost about 550–730 tokens. On a tiny task the baseline finishes first try with about 760
tokens, and that overhead roughly doubles the cost. Three small demo tasks are **not** a general savings claim.

## Limitations
- Anthropic adapter: implemented and contract-tested with fake transports, never live.
- Benchmark: three small tasks, n=3, one task blocked; no large-repository benchmark.
- Groq free tier (8,000 tokens/min plus a longer cap) makes live runs slow; the client waits out resets up to the
  configured limit and stops on longer ones (BLOCKED, never faked).
- Pre-flight false alarms are possible on unusual planner output. Several were found live and fixed with
  regressions; the two latest fixes (`z.ZodSchema.parse`, module-prefixed names) are verified locally and in CI, not
  yet live.
- Low-authority sources can still *support* a claim (noted, low confidence).
- The process sandbox fallback is weaker than Docker. It is labelled per run, and network isolation is present only
  where `unshare -rn` works. For hostile repositories, use Docker or a VM.
- The self-contained sandbox image was not built in this environment.

## Future work
- More LLM providers live-tested (Anthropic, others via the OpenAI-compatible adapter).
- More package ecosystems (Go, Rust, Java).
- Stronger semantic claim verification, more evidence providers.
- Larger, more diverse benchmark datasets on real repositories.
- Skip the planner for tasks with no third-party API use, to cut overhead on tiny tasks.
- More robust live browser testing (screenshots per screen in CI).
