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

---

# Final live round (branch `feat/vericode-live-final`, 2026-11-08)

Account limits seen in Groq's response headers: **8,000 tokens/minute**, 1,000 requests per window, and a longer
token cap. That cap is not shown in the headers, but it returned `retry-after` 160-1417 s while the per-minute bucket
was full. Every run below used real Groq (`openai/gpt-oss-120b`) and Tavily calls from GitHub Actions.

| Run | Commit | Scope | Outcome |
|---|---|---|---|
| [42446934192](https://github.com/Clint0-0/VeriCode/actions/runs/42446934192) | `222b1a8` | provider probes, Tavily, Track 1 A-D, Demo E, 3 coding tasks, browser | probes/Tavily/Track 1 OK; coding tasks hit 429 because of a wait-logic bug (fixed in `d27a59a`); browser 5/6 (test picked a task with no tokens; fixed) |
| [42447446549](https://github.com/Clint0-0/VeriCode/actions/runs/42447446549) | `d27a59a` | Track 1 B/D, Demo E, 3 coding tasks, browser | **all ACTUAL_SUCCESS**, browser **6/6** |
| [42448014676](https://github.com/Clint0-0/VeriCode/actions/runs/42448014676) | `44e47ac` | TS task, benchmark (3 tasks x 3 runs x 2 modes) | TS task passed; benchmark: 1 comparable task, the other 2 blocked by 429 |
| [42448651287](https://github.com/Clint0-0/VeriCode/actions/runs/42448651287) | `4bcbaa1` | TS task, benchmark summary+signup | **BLOCKED**: 429 `retry-after 610s` with a full per-minute bucket. Stopped as designed; browser 6/6 on persisted data |

## Priority 1 - live fixes

| Item | Result | Evidence |
|---|---|---|
| `pydantic.BaseModel.model_dump` import-path fix | ACTUAL AND SUCCESSFUL | no false NOT_FOUND in any live Python pre-flight (`false_not_found_model_dump: false`, runs 42446934192 and 42447446549) |
| Truncation detection + bounded retry | ACTUAL AND SUCCESSFUL | live probe: 48-token budget -> `finish_reason=length` detected, one escalation to 96, both calls counted with provider usage |
| TypeScript/zod task (new) | ACTUAL AND SUCCESSFUL | run 42447446549: first pass, 0 repairs, 4,097 tokens; run 42448014676: passed after 1 repair, 6,503 tokens |
| Python task (new, pydantic v2) | ACTUAL AND SUCCESSFUL | run 42447446549: passed after 2 repairs, 5,654 tokens (planner 838 / coder 2,084 / repair 2,732) |
| Demo C (arbitrary) | ACTUAL AND SUCCESSFUL | run 42447446549: first pass, 2,800 tokens |

Further pre-flight false alarms surfaced by these live runs, all fixed with regressions:
- `field_serializer('due')`: positional values were read as unknown keyword names.
- `z.object(...)` / `z.coerce.number`: namespace-object members and member paths were not resolved.
- An empty argument list was type-checked as a zero-argument call.
- Chained members (`z.coerce.number().int()`, `expect().toThrow()`) were not resolved; resolving them now also
  exposes the real `z.string().nonempty()` deprecation.

**The chained-member fixes (`de06c7c`, `ccb2482`) have not yet been confirmed live** (run 42448651287 was blocked).

## Priority 2 - Track 1 accuracy (live)

| Scenario | Before | After (runs 42446934192 / 42447446549) |
|---|---|---|
| B "latest stable Python is 3.10" | CONFLICTING_EVIDENCE | **CONTRADICTED**, correction **3.14**, from an authoritative page naming a newer version. Older 2020/2021 python.org pages are kept as "correct when published" |
| B pydantic "major version 1 / .dict()" | UNVERIFIED | UNVERIFIED (judge: insufficient); unchanged and honest |
| D "Rust will replace C by 2030" | CONTRADICTED (unknown-tier source, conf 43) | **UNVERIFIED**: only low-authority sources contradict it |
| D "PSF removes the GIL by 2027" | CONTRADICTED (unknown-tier, conf 34) | **UNVERIFIED** |
| Demo E `@validator` | CONFLICTING (installed code vs a lexical docs match) | **CONTRADICTED** by installed pydantic 2.9.2 |
| Demo E `BaseModel.model_dump()` | CONFLICTING | **CURRENT_SUPPORTED** (installed code + docs) |
| A, C | supported | unchanged; C still accepts low-authority support and says so in the explanation |

Rules added:
- Only primary/secondary, non-community sources may contradict a claim.
- A weak side is set aside against a strong side, and a disagreement between weak sources only is UNVERIFIED.
- A lexical match never overrides value, installed-code or judged evidence.
- Version monotonicity applies to "latest version" claims.
- An undated page with an equal or older value never overrides dated evidence.
- A value inside a negated sentence is not support.
- Product names map to their publisher (ChatGPT -> openai).

## Priority 3 - tokens (actual provider usage)

Changes:
- Compact planner output contract (planner output fell from 532 to 168-511 tokens per call in live runs).
- Optional `reasoning_effort` (`low` in the live workflow) for planner, judge and extraction only. The coder and
  repair settings are identical in both modes.
- The truncation retry now counts the truncated call.

Prompt context was already small; repairs were already targeted. No task, test or success criterion was changed.

**Run 42448014676, `users` task, 3 runs per mode, same model, snapshot, repair budget (3) and acceptance tests:**

| | Baseline | VeriCode |
|---|---|---|
| Final success | 3/3 | 3/3 |
| First-pass success | 0/3 | 2/3 |
| Repairs (mean) | 2.3 | 0.3 |
| Input tokens (mean) | 9,565.7 | 1,464 |
| Output tokens (mean) | 1,070 | 705 |
| **Total tokens (mean ± sd)** | **10,635.7 ± 3,717.1** | **2,169 ± 725.1** |
| Planning/verification overhead | 0 | 733 (planner 531 in / 206 out) |
| Duration (mean) | 57.6 s | 14.7 s |

**Token savings: 79.6%** (paired runs: 76.6%, 73.6%, 85.6%). The saving comes from avoided repairs: the baseline
resends the whole repository on each repair. This is **one task, n=3**. `summary` and `signup` (the TypeScript task
where the old code measured -250.3%) could not be re-measured on the optimised code because of 429s, so **no
TypeScript savings figure exists for the new code**.

## Priority 4 - browser over live data

`backend/tests/test_e2e_live.py` serves a copy of the live run's database and checks the screens in Chromium.
Expected values (analysis ids, live Tavily domains, task ids) are read from that database.
- Dashboard and token analytics show `ACTUAL_PROVIDER_USAGE`.
- The stale detector shows the live claim, status, source mode and the exact confidence index.
- The evidence explorer lists `live_tavily` sources from the DB.
- Task history and the pre-flight detail show actual usage.
- Workspace, pre-flight and settings render.
- No key appears in any API response, the page or the server log.

Result: **6/6 passed** in runs 42447446549 and 42448651287 (5/6 in 42446934192 before a test fix). The same test
fails on MOCK data, which shows it does not accept mock usage as real.

## Remaining blockers

| Item | Status (superseded, see the completion round below) | Action |
|---|---|---|
| Benchmark `summary` + `signup` on optimised code | BLOCKED (Groq 429, retry-after up to 1417 s) | After the Groq cap resets: Actions -> "Live validation" -> Run workflow on `feat/vericode-live-final` with `only=groq_text,groq_quota,benchmark_actual`, `skip_benchmark=false`, `bench_tasks=summary,signup`, `benchmark_runs=3` |
| Live confirmation of the chained-member pre-flight fixes | BLOCKED (same) | `only=groq_text,groq_quota,coding_typescript_new` |
| Anthropic provider live | not possible | no Anthropic key |
| Groq documentation | not consulted | fetching needed approval; behaviour verified against the real API instead |

---

# Completion round (2026-11-08, commit `18b9c81`)

| Run | Scope | Outcome |
|---|---|---|
| [42461511457](https://github.com/Clint0-0/VeriCode/actions/runs/42461511457) | TS task, benchmark `summary` + `signup`, browser | TS task passed; `summary` comparable; `signup` VeriCode 2/3 (one Groq 429); browser 4 passed / 2 skipped (no Track 1 data in this run) |
| [42462137064](https://github.com/Clint0-0/VeriCode/actions/runs/42462137064) | one re-run of `signup` | **BLOCKED**: 429 with retry-after up to 1,347 s. Not retried again |

**TypeScript/zod task (new): ACTUAL AND SUCCESSFUL.** First pass, 0 repairs, 2 files changed, tests pass, 3,026
actual tokens (planner 650 in / 503 out; coder 826 in / 1,047 out). Pre-flight: 7/7 planned APIs `VERIFIED_LOCAL`
(`z.object`, `z.coerce.number`, `z.string`, `z.preprocess`, vitest `describe`/`it`/`expect`), with no false alarms.
The planner didn't use a chained call in this run, so chained-call resolution (`z.string().nonempty()`,
`expect().toThrow()`) is verified by regression tests only.

**Benchmark (actual provider usage):**

| Task | Success B / V | First pass B / V | Repairs B / V | Baseline in / out (mean) | VeriCode in / out (mean) | VeriCode planner (mean) | Baseline total | VeriCode total | Savings |
|---|---|---|---|---|---|---|---|---|---|
| users | 3/3 / 3/3 | 0/3 / 2/3 | 2.3 / 0.3 | 9,565.7 / 1,070 | 1,464 / 705 | 531 in / 206 out | 10,635.7 ± 3,717.1 | 2,169 ± 725.1 | **79.6%** |
| summary | 3/3 / 3/3 | 2/3 / 3/3 | 0.3 / 0 | 3,438 / 503.3 | 1,499 / 488.7 | 564 in / 80 out | 3,941.3 ± 1,842.6 | 1,987.7 ± 150.4 | **49.6%** |
| signup (run 42491474776) | 3/3 / 3/3 | 3/3 / 3/3 | 0 / 0 | 560 / 207.3 | 1,325.7 / 512.7 | 582 in / 256 out (overhead 918) | 767.3 ± 38.6 | 1,838.3 ± 65.6 | **−139.6%** (pairs −154.7, −135.8, −129.2) |

No judge tokens are counted in coding benchmarks: the evidence judge is a Track 1 component, and the coding pipeline
makes no judge call. Tavily (external tool usage, counted separately and never as tokens) was called once in total: in one
`users` VeriCode run, for a documentation fallback. It was not called in `summary` or `signup`, and the baseline never
calls it.

---

# Final completion round (2026-11-08)

| Run | Commit | Scope | Outcome |
|---|---|---|---|
| [42465099749](https://github.com/Clint0-0/VeriCode/actions/runs/42465099749) | `cda4711` | chained-call TS task, `signup` benchmark | **chained task ACTUAL AND SUCCESSFUL**; `signup` BLOCKED (429, retry-after 76–166 s, above the 65 s wait limit then in force) |
| [42465458363](https://github.com/Clint0-0/VeriCode/actions/runs/42465458363) | `80a8e64` | chained task again (with the local-identifier fix), `signup` with a 180 s wait limit | **BLOCKED**: 429, retry-after 314–643 s. Not retried further |
| [42491474776](https://github.com/Clint0-0/VeriCode/actions/runs/42491474776) | `38ff1f5` | `signup` benchmark, 3 + 3 | **ACTUAL AND COMPARABLE**: −139.6%, both modes 3/3 first pass, no 429 |

**Chained-call TypeScript task** (`live_validation.TS_CHAIN_TASK`, installed zod 3.23.8, vitest 2.1.9, TypeScript 5.9.3),
run 42465099749:
- Passed first try, 0 repairs. 2 files written (`src/registration.ts`, `tests/registration.test.ts`); vitest passed.
- Tokens (provider-reported): planner 702 in / 594 out, coder 940 in / 575 out, 2,811 total.
- Pre-flight, re-checked per API with the compiler checker: **8 chained APIs resolved through call return types**,
  all `VERIFIED_LOCAL`:
  - `z.string().trim().min`, `z.string().email`, `z.coerce.number().int`, `z.coerce.number().int().positive`;
  - `z.string().min`, `z.array(…).default`;
  - `expect(…).toEqual`, `expect(…).toThrow`.
- One false alarm: `RegistrationSchema.parse` NOT_FOUND under zod (the schema the task creates). It is now
  UNCERTAIN "project-local identifier" (`80a8e64`).
- The partial second run showed two more false alarms: `z.ZodSchema.parse` (instance method through a namespace) and
  `vitest.expect.toThrow` (module repeated in the name). Both fixed in `b75a3bb`, with regression tests. These three
  fixes are **LOCAL · CI only**.
- `z.string().nonempty()` is reported DEPRECATED (installed zod marks it `@deprecated`) by the checker and the
  regression tests. The live plan used `min(1)` instead, so the deprecation was not exercised on a live plan.

**signup benchmark: ACTUAL AND COMPARABLE** (run [42491474776](https://github.com/Clint0-0/VeriCode/actions/runs/42491474776), `38ff1f5`, 2026-11-08). Fresh 3 + 3 set, no 429s:
baseline 3/3 first pass at 767.3 ± 38.6 tokens, VeriCode 3/3 first pass at 1,838.3 ± 65.6 tokens, savings **−139.6%**.
VeriCode costs more on this tiny task because nothing needed repairing. Earlier blocked attempts are listed above for history.
Groq quota seen in this run: 1,000 requests and 8,000 tokens per minute.

Rate-limit behaviour verified live: `retry-after` is honoured. Quota-stopped sections are classified BLOCKED, not
FAILED. Waits above the configured limit stop immediately instead of retrying.
