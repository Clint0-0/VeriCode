# Hackathon demo guide

Start: `scripts/run.sh` → open http://127.0.0.1:8000. Each demo can also be run headless with `scripts/demo.sh N`.

## Demo 1 — Pre-flight API detection
1. **Pre-Flight Inspector** → *Inspect* `sample_project`. It shows pydantic declared `>=1.10` and installed **2.9.2**
   (declared range ≠ installed version).
2. Load demo task `users` → *Run pre-flight*. It shows the validated skeleton: `Field(min_length,max_length,regex)`,
   `validator`, `BaseModel.dict`, plan assumed 1.10.
3. Expand findings:
   - **INCOMPATIBLE** `Field`: `regex` is rejected at `pydantic/fields.py:685`.
   - **DEPRECATED** `validator` → `field_validator`.
   - **DEPRECATED** `dict` → `model_dump`.
   - Live docs: Tavily evidence when a key is set, otherwise "not performed (missing_key)".
4. Show the surgical briefing.
5. **Coding Workspace** → demo task *Demo 1*, mode VeriCode → *Run task*. Watch the progress, the diff (`pattern=`,
   `@field_validator`, `model_dump`) and pytest passing (7 passed, deprecations are errors). Click *Apply to workspace* (optional).
6. Bonus: *Check a single API* → `pydantic.BaseSettings` → **NOT_FOUND** with the package's own migration
   message (moved to `pydantic-settings`).

## Demo 2 — General stale-answer detection
1. **Stale-Answer Detector** → *Load Demo 2 answer*.
2. Pick *Offline fixture* (reproducible, labelled) or *Live (Tavily)* if a key is configured.
3. Results:
   - claim_001 **CONTRADICTED**: newer python.org release than the claimed "latest" 3.12, with the older
     supporting page shown as superseded.
   - claim_002 **CURRENT_SUPPORTED** (past-event claim, so not stale despite old evidence).
   - claim_003 **UNVERIFIED** (no evidence).
   - claim_004 **NOT_APPLICABLE** (stable fact).
4. Expand claims to show freshness (formula + half-life), the confidence breakdown, and evidence with
   published date vs retrieved timestamp and source links.
5. *Generate corrected answer*: only claim_001 is rewritten, with citation [1]; claim_003 is marked `[unverified]`.
6. **Evidence Explorer** lists every source record.

To show non-software freshness in live mode, try an answer with prices or leadership, e.g.
"ChatGPT Plus costs $20 per month. Satya Nadella is the CEO of Microsoft." with preferred domains `openai.com, microsoft.com`.

## Demo 3 — Token-efficient coding agent vs baseline
1. **Token Analytics** → *Run benchmark* (3 runs/mode).
2. For each task, compare baseline and VeriCode: total tokens (with planner overhead included), first-pass success,
   repairs, LLM calls, tokens by stage. Detection rate and false-positive rate are shown for Demo 1.
3. Point out the `measurement` badge (estimated with the mock; provider-reported with a real key) and that savings
   are only shown when both modes succeed.
4. **Task History** → open any run to inspect its context files, prompt stages and diff.
