# Benchmark methodology

Version 2 (2026-11-13): 12 tasks, four configurations, paired repetitions, resumable batches. Version 1 results
(3 demo tasks, two modes) are kept unchanged under [Historical results](#historical-results-version-1).

## Configurations

| Configuration | Context | Planner + pre-flight | Post-generation API audit | Repair prompt |
|---|---|---|---|---|
| `baseline` | every source file in the repository | no | no | full repository + failure output |
| `vericode_full` | relevant files only | always | no | failure digest + changed files + briefing |
| `vericode_adaptive` | relevant files only | only when the risk gate sees possible third-party API involvement | yes, after every attempt | as above, plus audit findings |
| `context_only` (ablation) | relevant files only | no | no | as above |

`vericode_full` is the original VeriCode pipeline, unchanged (same prompt text), so its numbers are directly
comparable with version 1. `vericode` in the UI/API means `vericode_adaptive` (setting `adaptive_execution`,
default on) or `vericode_full` when the setting is off.

### Adaptive execution (why and how)
The live signup run showed where VeriCode loses on easy tasks: the planner call (~840 tokens) costs more than a
small baseline prompt. Trimming the coder prompt cannot fix that (the remaining extras are ~180 tokens).

* **Risk gate** (`backend/vericode/api_risk.py`). The planner is skipped only with positive evidence of no
  third-party API involvement: the project has a test command, and the task names no dependency, no import name of
  one, no identifier the project imports from a third-party package, no dependency wording (library, upgrade,
  migrate, deprecated, import, version, SDK, install, HTTP ...) and no capability word of an installed dependency
  (pydantic: model, validator, schema, json ...; zod: schema, validate, parse ...). The vocabulary over-approximates
  on purpose: a false "high" only costs the planner call. On the 12-task dataset the gate agrees with the dataset's
  ground-truth `api_risk` label on every task (tested in `test_benchmark_evidence.py`).
* **Post-generation audit** (`backend/vericode/api_audit.py`, `tools/ts-checker/audit.cjs`). After every coder
  attempt, the third-party APIs the generated code actually uses are verified against the installed packages, on
  added lines only, with no LLM call: Python through `ast` + the same installed-source resolver as the pre-flight
  (including methods called on subclasses/instances of third-party classes); TypeScript through the TypeScript
  compiler over the real files (deprecated symbols and overloads, missing exports/members, wrong calls on
  `node_modules` symbols). Audit problems are repaired like failing tests. So the fast path never skips
  verification: it moves it from a predicted plan (LLM call) to the written code (no LLM call).

## Held constant (fairness)
Provider, model and settings; task prompt; a pristine copy of the same repository snapshot per run (content
fingerprint recorded in every run record); the task's seed files (e.g. a seeded bug) and acceptance tests; the
validation commands; the repair budget (`max_repairs`, default 3); command timeouts; the coder system prompt and
output budget. Repetitions are interleaved (rep 1 of every configuration, then rep 2 ...) and the configuration
order rotates per repetition, so no configuration systematically runs first against a warming cache or a draining
rate-limit window.

Intentional differences are the configurations themselves (context and pre-flight). One provider-imposed
difference: Groq's free tier caps a single request at 8,000 tokens including the requested output budget. A
request rejected with HTTP 413 is retried once with the output budget reduced by the stated excess (any
configuration); if fewer than 512 output tokens would remain, the run is **BLOCKED**, not failed. The whole-
repository baseline on the large repository is close to this cap.

## Measurement
Every LLM call is counted (planner, coder, repairs) with input and output separated, and labelled
`ACTUAL_PROVIDER_USAGE` (usage returned by the provider), `ESTIMATED` (real provider without usage, chars/4) or
`MOCK` (scripted offline provider). Labels are never combined in one figure: a pair with different labels is
excluded, and a group with mixed labels is reported as `MIXED` with no saving. Tavily is reported separately as
search calls; no token cost is invented for it.

Per run record (`runs.jsonl`): status (`SUCCESS` / `FAILED` / `BLOCKED`), success and first-pass success, repairs,
test pass rate, execution path (`baseline` / `full` / `fast` / `context_only`), risk, total/input/output tokens,
LLM calls, tokens by stage (planner/coder/repair), duration and per-stage timings, search calls, API problems in
the final code (audited identically for every configuration), the snapshot fingerprint, and any error.

**Token savings** for repetition *i* = `(baseline_i − config_i) / baseline_i × 100`, computed only when both runs
succeeded and carry the same measurement label. Failed or blocked runs produce no saving; they are reported as
success rates and failure details. Per task: mean, median, standard deviation and n of the paired savings, a
token-weighted mean over the pairs, and a 95% t-interval only when n ≥ 5 (labelled exploratory below n = 10).
Negative savings are kept. Overall: token-weighted saving over all pairs, median of per-task savings, and the
number of tasks where the configuration used more tokens than the baseline.

## Dataset (12 tasks, `demos/tasks/catalog.json`)

| Task | Repo | Size | Lang | Category | API risk | Expected change |
|---|---|---|---|---|---|---|
| users | sample_project | small (~2.2k tok) | Python | feature | dependency (pydantic) | new pydantic v2 `User` model |
| summary | sample_project | small | Python | feature | none | `TaskStore.priority_summary()` |
| signup | ts_project | small (~0.3k tok) | TS | feature | dependency (zod) | zod signup schema |
| ord_schema | ts_orders | medium (~2.4k tok) | TS | feature | dependency (zod) | checkout + business-address schemas, `parseCheckout` |
| ord_bugfix | ts_orders | medium | TS | bug fix (seeded) | none | two operators in `calculateShipping` |
| ord_modify | ts_orders | medium | TS | modification | none | discount ordering + zero floor |
| inv_restock | py_inventory | medium (~2.9k tok) | Python | feature | dependency (pydantic) | `RestockRequest` + service method |
| inv_refactor | py_inventory | medium | Python | refactor | none | extract duplicated discount + VAT logic |
| inv_tests | py_inventory | medium | Python | test writing | test framework (pytest) | `tests/test_reports.py`, mutation-checked |
| led_fx_bugfix | py_ledger | large (~7.2k tok) | Python | bug fix (seeded) | none | historical FX rate lookup |
| led_export | py_ledger | large | Python | feature | dependency (pydantic) | JSON export/import of journal entries |
| led_cashflow | py_ledger | large | Python | feature | none | monthly cash-flow report |

Sizes are the whole-repository prompt context (source + tests, chars/4). Pinned dependencies: pydantic 2.9.2,
pytest 8.3.3 (new Python repos), zod 3.23.8, vitest 2.1.9, TypeScript 5.9.3. Every task records its expected
changes, acceptance tests and expected API findings in the catalog. Dependency-API acceptance tests treat warnings
as errors, so deprecated (v1-style) pydantic code fails for every configuration alike.

**Validity:** for every new task, `backend/tests/test_benchmark_tasks.py` proves that the pristine project passes,
the task's starting state fails its acceptance tests, and a reference solution (`demos/tasks/<id>/reference/`,
never shown to an agent) passes everything. Runs in key-free CI.

**Provenance:** the three new repositories are original code written for this benchmark. Using pinned
open-source snapshots was attempted (TinyDB 4.8.2), but executing downloaded third-party code was not permitted in
the build environment, so no third-party source is included. All repositories run offline; CI never needs GitHub
or package-registry access beyond installing the pinned dependencies.

## Running
```
python -m vericode.bench_cli --plan --request-cap 8000                # ESTIMATED usage, no LLM calls
python -m vericode.bench_cli --runs 3 --records runs.jsonl --max-tokens 150000 --out results/
python -m vericode.bench_cli --report-only --records runs.jsonl --out results/
```
Re-running with the same `--records` skips completed runs (BLOCKED runs are retried). A batch stops starting new
runs when the token or run budget is exhausted, when the provider blocks a run, or when the machine cannot run the
checks (structured `error_detail`, e.g. missing npm or `node_modules`); the remaining runs are recorded
as BLOCKED (not run). In GitHub Actions: workflow **Benchmark (real provider)** (manual), or from a branch through
**Live validation** with `only=benchmark` (inputs `bench_tasks`, `benchmark_runs`, `bench_configurations`,
`bench_max_tokens`, `bench_resume_from_run`; `skip_benchmark=plan` prints the estimate only). Records, summary and
report are uploaded as the `benchmark-results` artifact and printed in the job log.

Results: [submission/benchmark-results/](submission/benchmark-results/).

## Historical results (version 1)
Groq `openai/gpt-oss-120b`, 3 runs per mode, original two-mode benchmark (`baseline` vs the original
`vericode`, which equals today's `vericode_full`). Not re-labelled and not merged with version 2 figures.
- `users`: 79.6% savings (run 42448014676).
- `summary`: 49.6% savings (run 42461511457).
- `signup`: −139.6% (VeriCode costs more; baseline 767 vs VeriCode 1,838 tokens, both 3/3 first pass), run
  [42491474776](https://github.com/Clint0-0/VeriCode/actions/runs/42491474776).
