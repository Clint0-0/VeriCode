# Benchmark results, 2026-11-13 (version 2 benchmark, first batches)

All figures are **ACTUAL_PROVIDER_USAGE** (token counts returned by Groq), computed from the run records in
[`runs.jsonl`](runs.jsonl) by `python -m vericode.bench_cli --report-only`; generated tables:
[`report.md`](report.md), machine-readable: [`summary.json`](summary.json). Small samples (n ≤ 3 per task):
**exploratory**, not a general claim. These are new results; version 1 results are listed separately in
[BENCHMARK.md](../../../BENCHMARK.md#historical-results-version-1) and are not merged into these tables.

## 1. Method
Paired, interleaved repetitions with rotating configuration order; every configuration gets the same model and
settings, task prompt, pristine copy of the same repository snapshot (fingerprint per record), seed files,
acceptance tests, validation commands, repair budget (3) and timeouts. A saving is computed per repetition only when
both the configuration's run and the baseline's run succeeded with the same measurement label. Full method:
[BENCHMARK.md](../../../BENCHMARK.md).

## 2–3. Dataset and complexity
12 tasks in 5 repositories: small (sample_project ~2.2k tokens, ts_project ~0.3k), medium (ts_orders ~2.4k,
py_inventory ~2.9k), large (py_ledger ~7.2k); Python and TypeScript; feature, modification, seeded bug fix,
refactor and mutation-checked test-writing tasks; 6 with dependency-API risk, 6 without. Table and validity checks:
[BENCHMARK.md → Dataset](../../../BENCHMARK.md#dataset-12-tasks-demostaskscatalogjson).

## 4. Model and provider
Groq, OpenAI-compatible endpoint, `openai/gpt-oss-120b` for planner and coder (repository variables; Groq's own
HTTP 413 response in run 43383744860 names the model). Default reasoning effort, streaming coder, output budget
4,000 tokens per coder call. Account limits observed in the response headers: 8,000 tokens per minute, 1,000
requests per day, and a rolling daily token cap (HTTP 429 with retry-after 382 s after ~211k tokens in two batches).
Tavily documentation lookups were enabled; Tavily calls are not counted as tokens.

## 5. Repetitions
Configurations `baseline`, `vericode_full` (original VeriCode), `vericode_adaptive`; 3 repetitions each.
Completed: **summary, signup, ord_bugfix, inv_refactor** (3/3/3); **inv_restock** (baseline 3, full 3, adaptive 0:
re-run pending, see §11); **users** (1/1/1). Not run yet (daily quota): ord_schema, ord_modify, inv_tests,
led_fx_bugfix, led_export, led_cashflow, and the `context_only` ablation. 45 runs completed (43 succeeded, 2 failed).

## 6–7. Actual tokens and comparison (mean tokens per run; paired savings vs baseline)

| Task | Size / lang | Baseline | VeriCode full | VeriCode adaptive (path) | Full: paired savings | Adaptive: paired savings |
|---|---|---|---|---|---|---|
| summary | small / Py | 4,959 | 2,428 | **1,250** (fast) | 62.7, 66.1, −6.2 → 51.0% | 79.0, 80.0, 54.7 → **74.8%** |
| signup | small / TS | **808** | 2,475 | 2,238 (full) | −133.3, −341.0, −158.1 → −206.5% | −171.9, −189.4, −171.4 → −177.1% |
| ord_bugfix | medium / TS | 3,418 | 3,257 | 3,337* (fast) | 2.4, 5.4, 6.3 → 4.7% | 44.9, 46.3 (n=2) → 45.6% |
| inv_refactor | medium / Py | 4,152 | 3,113 | **2,458** (fast) | 21.3, 14.4, 38.2 → 25.0% | 30.1, 53.3, 39.3 → **40.8%** |
| inv_restock | medium / Py | 9,291 | 7,364* | pending | 46.3, 48.4 (n=2) → 47.3% | — |
| users | small / Py | 6,840 | 3,103 | 1,911 (full) | 54.6 (n=1) | 72.1 (n=1) |

\* includes a failed run (mean over completed runs); failed runs never enter a saving. Per-task "→" values are
token-weighted over the successful pairs. **Overall (all successful pairs):** adaptive **46.0%** token-weighted
(12 pairs, 5 tasks, median task 45.6%); full **28.7%** (15 pairs, 6 tasks, median task 36.1%). Negative result
kept: **signup costs VeriCode about 2.8× (adaptive) to 3.1× (full) the baseline.** The baseline is 808 tokens and
passes first time; any planner call dominates.

## 8. Per-stage breakdown (mean tokens per run)

| Task | Configuration | Planner | Coder | Repair | Input / output | LLM calls |
|---|---|---|---|---|---|---|
| summary | baseline / full / adaptive | 0 / 1,092 / **0** | 2,821 / 1,336 / 1,250 | 2,137 / 0 / 0 | 4,375/584 · 1,674/754 · 909/341 | 1.7 / 2.3 / 1 |
| signup | baseline / full / adaptive | 0 / 1,529 / 1,337 | 808 / 946 / 901 | 0 / 0 / 0 | 560/248 · 1,506/970 · 1,264/974 | 1 / 2.3 / 2 |
| ord_bugfix | baseline / full / adaptive | 0 / 1,326 / **0** | 3,418 / 1,931 / 1,880 | 0 / 0 / 1,457* | 2,806/612 · 2,041/1,216 · 1,629/1,708 | 1 / 2 / 2 |
| inv_refactor | baseline / full / adaptive | 0 / 684 / **0** | 4,152 / 2,428 / 2,458 | 0 / 0 / 0 | 3,179/973 · 1,474/1,639 · 868/1,590 | 1 / 2 / 1 |
| inv_restock | baseline / full | 0 / 1,529 | 4,854 / 3,368 | 4,436 / 2,466 | 6,794/2,497 · 4,401/2,963 | 2 / 3 |

Where the tokens go: targeted context cuts coder **input** sharply (e.g. inv_refactor 3,179 → 868), but
gpt-oss-120b's **output** (which includes hidden reasoning) is often larger for VeriCode prompts than for the
baseline (inv_refactor 973 → 1,590–1,639; signup 248 → ~970). The baseline's cost is dominated by repairs that
resend the whole repository (summary, inv_restock).

## 9. Success rates

| Configuration | Runs | Success | First-pass success | Repairs per run |
|---|---|---|---|---|
| baseline | 16 | 16/16 | 10/16 | 0.38 |
| vericode_full | 16 | 15/16 | 14/16 | 0.25 |
| vericode_adaptive | 13 | 12/13 | 12/13 | 0.23 |

Total ACTUAL tokens in the kept records: 163,490 (plus 47,040 in the three discarded runs, §11). API problems
in final code (audited identically for every configuration, TypeScript tasks and post-fix Python runs): 0 in every
configuration.

## 10. Ablation (what saves, what costs)
* **Planner skip (adaptive fast path vs full) on the 3 fast-path tasks:** removes 684–1,326 planner tokens per run;
  token-weighted, adaptive uses **48.5% fewer tokens than full on summary, 21.0% on inv_refactor and 42.5% on
  ord_bugfix's successful runs**. Cost: 1 of 9 fast-path runs failed (ord_bugfix rep 3, 3 repairs, 6,265 tokens)
  vs 0 of 9 for the full path on the same tasks. Too few runs to tell a real regression from noise; flagged.
* **Compact prompt on the full path (adaptive full vs full):** signup 2,238 vs 2,475 mean, with a much smaller
  spread (sd 54 vs 742), and users 1,911 vs 3,103 (n=1).
* **Audit:** detected nothing in final code on these tasks (no deprecated API slipped through), so it cost no
  repairs after the fix in §11. Its value shows when a model writes deprecated code (unit tests and the mock demo).
* **`context_only`** (targeted context, no pre-flight, no audit): **not run** (quota). Without it, the share of
  savings due to targeted context alone versus pre-flight is not yet separated by measurement.

## 11. Limitations and unsuccessful experiments
* **Audit false positive (fixed, runs discarded).** In batch 1 (code `fde7661`), the audit read `self.<field>` in a
  pydantic model as `pydantic.BaseModel.<field>` and reported NOT_FOUND. On inv_restock the adaptive path then
  forced needless repairs: **19,170 / 15,563 / 12,307 tokens** vs ~5,000 for the full path. Fixed in `ba29295`
  (class-body names and self-assigned attributes are local; dynamic members are only reported when found and
  problematic). The three runs were discarded with `--drop` (kept in the run artifact as `runs.dropped.jsonl`) and
  their re-run was blocked by the daily quota. "API problems shipped" values produced by the defective audit on
  Python tasks were removed from the records (marked with a `note`).
* **Large repository blocked for the baseline.** led_fx_bugfix baseline: Groq rejected the whole-repository prompt
  with HTTP 413 (8,000-token per-request cap including the output budget). The fit-and-retry did not trigger because
  the limit numbers sat past a 400-character error cut (fixed in `ba29295`). That block also stopped batch 1 (now:
  size blocks no longer stop a batch). No large-repository task has been measured yet.
* **Quota.** Batch 2 stopped after 3 runs on a 429 with retry-after 382 s; the remaining 77 runs are recorded as
  BLOCKED (not run). At ~200k tokens per day the full 4-configuration matrix (~660k ESTIMATED) needs about 3–4
  days of resumed batches.
* **Open-source snapshots** were not used: running a downloaded project's test suite (TinyDB 4.8.2) was not permitted
  in the build environment. The new repositories are original code.
* **Sample size:** n ≤ 3 per task and configuration; no confidence intervals are reported (they need n ≥ 5).
* **Single model** (`openai/gpt-oss-120b`); results may differ for models that spend fewer reasoning tokens.

## 12. Traceability
* Batch 1: Live validation run [43383744860](https://github.com/Clint0-0/VeriCode/actions/runs/43383744860)
  (code `fde7661`), artifact `benchmark-results`.
* Batch 2 (resume of batch 1, drop `inv_restock:vericode_adaptive`): run
  [43386909599](https://github.com/Clint0-0/VeriCode/actions/runs/43386909599) (code `ba29295`), artifact
  `benchmark-results` (includes the dropped records).
* Plan (ESTIMATED usage, no LLM calls): run [43383594201](https://github.com/Clint0-0/VeriCode/actions/runs/43383594201).

**Resume:** Actions → *Live validation* → Run workflow on `feat/vericode-benchmark-evidence` with `only=benchmark`,
`skip_benchmark=true`, `benchmark_runs=3`, `bench_resume_from_run=43386909599`, `bench_drop` empty, and
`bench_max_tokens=180000`. Repeat daily with the previous run id; then once with
`bench_configurations=baseline,context_only` for the ablation. Regenerate this report from the newest
`runs.jsonl` with `python -m vericode.bench_cli --report-only --records runs.jsonl --out <dir>`.
