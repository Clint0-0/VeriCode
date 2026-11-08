# Benchmark methodology

**Modes**
- *baseline*: a conventional agent. The prompt contains the task plus **every source file in the repository**.
  No planner and no verification. On failure it re-sends the full repository plus the failure output.
- *vericode*: relevant files only, a planner skeleton, local and live verification, a compact briefing.
  On failure it sends the failure digest plus the files it changed.

**Held constant:** provider and model configuration, task prompt, pristine repository copy per run, acceptance
tests (copied into the sandbox from `demos/tasks/`), validation commands, and repair budget (`max_repairs`, default 3).

**Measurement classes:** every LLM call is labelled `ACTUAL_PROVIDER_USAGE` (usage returned by the provider API),
`ESTIMATED` (real provider, usage missing → chars/4) or `MOCK` (scripted offline provider). A run or benchmark takes
the weakest label among its calls. The UI and `/api/benchmarks` keep `ACTUAL_PROVIDER_USAGE` results separate
from mock and estimated results.

**Counted:** every LLM call, recorded per stage (`planner`, `coder`, `repair`, and `claim_extraction`/`claim_judge`
if used) with input and output separated. Provider-reported usage is used when the API returns it
(Anthropic `usage.input_tokens/output_tokens` including cache read/creation; OpenAI
`usage.prompt_tokens/completion_tokens`). Otherwise the call is flagged `estimated` (chars/4), and the run's
`measurement` becomes `estimated`. Tavily is reported separately as `search_calls`; no token cost is invented for it.

**Savings** = `(baseline_mean_total − vericode_mean_total) / baseline_mean_total × 100`, per task, computed
**only if every run of both modes succeeded**. Otherwise the result reads `n/a` with the reason.

**Aggregates:** per-task mean ± sd (min/max, n), per-run paired savings, verification-overhead tokens (planner and
judge stages), and the average savings across comparable tasks with its spread.

**Quality signal:** for each paired run, the APIs VeriCode's pre-flight flagged are searched in each mode's final
diff (`flagged_api_usage`). A baseline can "succeed" while shipping deprecated APIs that tests don't catch; this
metric makes that visible.

**Also reported:** final and first-pass success rates, repair attempts, LLM calls, search calls, duration
(mean ± sd, min/max, n), tokens by stage, and API-incompatibility detection rate / false-positive rate against
`expected_findings` in `demos/tasks/catalog.json`.

**Run:** `scripts/demo.sh 3 --runs 3`, or the Token Analytics screen, or `POST /api/benchmarks`.

**Caveat:** with the mock provider, outputs are deterministic and token counts are estimates. The numbers show
the pipeline mechanics and the context difference only. Report real-model numbers only from runs whose
`measurement` is `provider-reported usage`.

## Actual results (Groq `openai/gpt-oss-120b`, 3 runs per mode)
Measured with `python -m vericode.live_validation --only benchmark_actual --bench-tasks ...` in the manual
"Live validation" workflow. Results and caveats are in [README → Measured results](../README.md#measured-results-honest)
and [LIVE_VALIDATION.md](LIVE_VALIDATION.md):
- `users`: 79.6% savings.
- `summary`: 49.6% savings.
- `signup`: −139.6% (VeriCode costs more; baseline 767 vs VeriCode 1,838 tokens, both 3/3 first pass), run [42491474776](https://github.com/Clint0-0/VeriCode/actions/runs/42491474776).

Three small demo tasks are not a general savings claim. On a free Groq account, expect HTTP 429 waits: the client
waits out short per-minute resets and stops on long ones.
