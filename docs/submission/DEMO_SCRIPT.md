# Demo script (5–7 minutes)

Setup before the demo: `scripts/setup.sh`, then `scripts/run.sh`, and open the printed login URL. With keys in
`.env` (Groq through the OpenAI-compatible settings + Tavily; see README) the live paths work. Without keys, use
`scripts/demo.sh offline`, and **say out loud that results are FIXTURE/MOCK**. Show only results the app actually
produces; the numbers below are from recorded live runs ([RESULTS_AND_LIMITATIONS.md](RESULTS_AND_LIMITATIONS.md)).

| Time | Step | What to show | What to say |
|---|---|---|---|
| 0:00–0:45 | The problem | Dashboard | Models trust knowledge that has aged: stale facts in answers, outdated APIs in generated code. VeriCode verifies before trusting or generating. |
| 0:45–2:15 | Track 1: stale answer | Stale-Answer Detector → paste "The latest stable version of Python is 3.10. FastAPI supports async path operation functions." → *Live (Tavily)* | Claims with spans; only volatile claims searched. Python claim → **CONTRADICTED** with a correction, the source and a verbatim quote; old python.org pages shown as "correct when published". FastAPI → **CURRENT_SUPPORTED**. Point at **freshness vs confidence**: an old page can still support a true claim. |
| 2:15–3:00 | Evidence explorer | Evidence screen | Every source is persisted with its authority tier, published date, retrieval time and origin `live_tavily`. |
| 3:00–4:00 | Track 2: outdated API caught before generation | Pre-Flight Inspector on `demos/sample_project` with "Create a Pydantic model with a field validator that lowercases emails, using @validator and Field(regex=...)" | Planner's API skeleton is verified against **installed pydantic 2.9.2**: `@validator` DEPRECATED, `Field(regex=)` INCOMPATIBLE, with installed-source locations. No code was generated yet. |
| 4:00–5:00 | Valid task passes pre-flight | Coding Workspace on `demos/ts_project`, the chained zod task from `live_validation.TS_CHAIN_TASK` | Chained calls like `z.coerce.number().int().positive()` and `expect(() => …).toThrow()` resolved by the TypeScript compiler against installed zod 3.23.8 / vitest 2.1.9; tests pass in the sandbox; diff and tokens by stage. |
| 5:00–6:15 | Token analytics | Token Analytics → actual benchmark | Actual Groq usage, never mixed with mock. `users`: 79.6% fewer tokens, `summary`: 49.6% fewer, both from avoided repairs. `signup` (tiny task): VeriCode's planning overhead made it about 2.4x more expensive (−139.6%, 3/3 both modes). Say plainly that three small tasks are not a general claim. |
| 6:15–7:00 | Why combined | Stale detector with workspace `sample_project`: "To validate fields in Pydantic, use the @validator decorator." | The same installed-package verifier is Track 1 evidence: CONTRADICTED by installed pydantic 2.9.2, not by web opinion. One principle, two tracks. |

Fallbacks if live calls hit rate limits: switch Track 1 to *Offline fixture* and use `scripts/demo.sh offline` for
Track 2, and say the results are FIXTURE/MOCK.
