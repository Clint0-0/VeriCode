# Live validation report (Groq + Tavily)

Branch `feat/vericode-live-validation`, 2026-11-07/08. Every live request ran in GitHub Actions
(`.github/workflows/live.yml`, manual) using repo **secrets** `TAVILY_API_KEY`, `OPENAI_API_KEY` (a Groq key) and
repo **variables** `VERICODE_LLM_PROVIDER=openai`, `OPENAI_BASE_URL=https://api.groq.com/openai/v1`,
`VERICODE_CODER_MODEL` / `VERICODE_PLANNER_MODEL` = `openai/gpt-oss-120b`. The build workspace itself cannot reach
`api.groq.com` or `api.tavily.com` (egress proxy), so nothing here was run from a local `.env`.

The harness is `backend/vericode/live_validation.py`. It never falls back to MOCK or fixtures, labels every
section `ACTUAL_SUCCESS` / `ACTUAL_FAILED` / `BLOCKED`, and refuses to write its report if any configured key value
appears in it.

| Run | Commit | What it shows |
|---|---|---|
| [42397432837](https://github.com/Clint0-0/VeriCode/actions/runs/42397432837) | `a655be9` | Live tests 2/2, demos D/C/3 - the only run with usable **actual-token benchmark** numbers |
| [42401454502](https://github.com/Clint0-0/VeriCode/actions/runs/42401454502) | `9141a25` | Full harness: provider, Tavily, Track 1 A-D, Demo E, 3 coding tasks, API screens. Found 2 bugs (fixed after) |
| [42403530801](https://github.com/Clint0-0/VeriCode/actions/runs/42403530801) | `88608f6` | Re-run with fixes: **Groq HTTP 429 (account rate limit)** on most model calls - fixes not yet confirmed live |

## Results (run 42401454502 unless noted)

| # | Item | Classification | Evidence |
|---|---|---|---|
| 1 | Groq configuration | ACTUAL AND SUCCESSFUL | provider `openai` (OpenAI-compatible adapter), endpoint host `api.groq.com`, `GET /models` 200, configured model listed for the account |
| 2 | Text completion | ACTUAL AND SUCCESSFUL | reply `pong`; 85 in / 37 out tokens, `ACTUAL_PROVIDER_USAGE` |
| 3 | Structured planner (schema-validated JSON) | ACTUAL AND SUCCESSFUL | 231 in / 532 out; API skeleton generation 428 in / 765 out, 0 schema retries |
| 4 | Streaming (coder stage, `stream_options.include_usage`) | ACTUAL AND SUCCESSFUL | usage arrived in the stream: 97 in / 99 out, not ESTIMATED |
| 5 | Error handling | ACTUAL AND SUCCESSFUL | invalid model id -> clear `HTTP 404 model_not_found`; no key in the message |
| 6 | Evidence judge (structured) | ACTUAL AND SUCCESSFUL | verdict `supports`, quote "Python 3.13.0 was released on October 7, 2024." verified verbatim in the source; 473 in / 214 out |
| 7 | Tavily search | ACTUAL AND SUCCESSFUL | 3 results (docs.python.org, realpython.com, python.org), valid https URLs, `published_date` kept when given, `retrieved_at` recorded, 1 credit, rows persisted in `search_usage` |
| 8 | Tavily extract | ACTUAL AND SUCCESSFUL | 122,070 chars from docs.python.org/3/whatsnew/3.13.html |
| 9 | Track 1 A - current facts | ACTUAL AND SUCCESSFUL | both claims `CURRENT_SUPPORTED`; FastAPI claim supported by an LLM-judged primary source with **freshness 0.0** (2018 page) yet confidence 65.8 - freshness is not truth |
| 10 | Track 1 B - outdated facts | ACTUAL, PARTIAL | "latest Python is 3.10" -> `CONFLICTING_EVIDENCE` (a 2021 python.org page supports it, an undated python.org page contradicts it; recency cannot settle an undated source). Pydantic "major version 1 / .dict()" -> `UNVERIFIED` (judge: insufficient). Correct-answer generation flagged both, rewrote nothing. Not flagged as plainly `CONTRADICTED` - see limitations |
| 11 | Track 1 C - semantic claims | ACTUAL AND SUCCESSFUL | Groq OpenAI-compatibility claim `CURRENT_SUPPORTED` via LLM judge with a verbatim quote; Tavily-results claim `UNVERIFIED` because the judge's verdict lacked a verbatim quote and was **discarded** |
| 12 | Track 1 D - conflicting/insufficient | ACTUAL, PARTIAL | both forward-looking claims `CONTRADICTED` via LLM judge (quotes verified), but the deciding sources are `unknown`-tier with confidence 33.7-43.0 |
| 13 | Demo E (installed source + Tavily + judge) | ACTUAL AND SUCCESSFUL | pydantic 2.9.2: `@validator` contradicted locally (deprecated), `BaseSettings` from pydantic contradicted locally, `model_dump()` supported locally and externally; zod 3.23.8 claim checked against installed declarations. Every conclusion lists its origin (`installed_source`, `live_tavily`). Original answer not rewritten |
| 14 | Python coding task (new: pydantic v2 `TaskExport`, frozen model, `field_serializer`, JSON dump, tests) | ACTUAL AND SUCCESSFUL | first pass, 0 repairs, 2 files, tests pass, 4,434 actual tokens (planner 1,699 / coder 2,735). **Bug found**: pre-flight falsely said `pydantic.BaseModel.model_dump` NOT_FOUND, and the coder added a pointless `AttributeError` fallback. Fixed in `4bb0821` |
| 15 | TypeScript coding task (new: zod `AppConfig` with coerce/defaults, `parseConfig`, vitest) | ACTUAL AND FAILED | planner JSON truncated at 1,200 output tokens three times (5,316 tokens spent). Fixed in `7de7a8b` (truncation detection + one bounded budget increase). Re-run hit 429 - **fix unconfirmed live** |
| 16 | Arbitrary task (Demo C `due_within`) | ACTUAL AND SUCCESSFUL | first pass, 0 repairs, tests pass, 3,322 actual tokens |
| 17 | Actual-token benchmark | ACTUAL, PARTIAL | see below; run 42403530801's benchmark is ACTUAL AND FAILED (429 on every task) |
| 18 | API data behind the 8 screens | ACTUAL AND SUCCESSFUL | dashboard, settings, integrations, task history, stale history/detail, evidence explorer, token analytics, benchmarks, pre-flight inspector: all HTTP 200, real results persisted and labelled `ACTUAL_PROVIDER_USAGE`, no key in any response |

## Actual-token benchmark (run 42397432837, commit `a655be9`, 3 runs per mode)

Same model (`openai/gpt-oss-120b`), same repository snapshot, same task, same repair budget (3), same tests.

| Task | Baseline success | VeriCode success | Baseline tokens (mean ± sd) | VeriCode tokens (mean ± sd) | Savings |
|---|---|---|---|---|---|
| users (pydantic v1 APIs planned) | 33% | 100% | 5,449.7 ± 7,033.9 | 4,316.3 ± 902.3 | not computed (baseline failed 2/3) |
| summary (no API risk) | 67% | 100% | 2,874 ± 31.2 | 2,713.3 ± 712.3 | not computed (baseline failed 1/3) |
| signup (TypeScript zod) | 100% | 100% | 776.7 ± 58.0 | 2,721 ± 68.5 | **-250.3%** |

Reading: VeriCode completed every run; the conventional workflow failed 3 of 9. On the only task where both modes
always succeeded, VeriCode used 3.5x the tokens - its planning/verification overhead is larger than anything it saves
on a 3-file repository. **No positive token-savings figure has been measured.** Per-stage input/output splits and
durations are produced by the harness (`benchmark_actual`), but the run that would have recorded them was
rate-limited.

## Remaining failures and what is needed

| Item | Status | Human action |
|---|---|---|
| Confirm the truncation fix (TS task) and the import-path fix live | BLOCKED (Groq 429) | Wait for the Groq limit to reset (console.groq.com -> Settings -> Limits), then Actions -> "Live validation" -> Run workflow on `feat/vericode-live-validation` with `only=groq_skeleton,groq_evidence_judge,coding_python_new,coding_typescript_new,coding_arbitrary_demoC`, `skip_benchmark=true` |
| Benchmark with per-stage splits on fixed code | BLOCKED (Groq 429) | Same workflow, `only=benchmark_actual`, `skip_benchmark=false`, `benchmark_runs=3`. Expect roughly 60-120k tokens |
| Groq docs not consulted during this run | not done (fetch needed approval) | Behaviour was verified empirically against the real API instead |
| Browser (Playwright) pass over real persisted data | not done | API layer behind every screen was checked live; e2e still runs on mock data in key-free CI |
