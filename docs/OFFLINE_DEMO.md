# Offline demonstration guide (no API keys)

Everything below runs without `TAVILY_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or model ids. Every result is labelled:

| Label | Meaning |
|---|---|
| `MOCK` | Scripted offline coder. It recognises only the 3 bundled tasks and does not reason. Token counts are **estimates** (chars/4) |
| `ESTIMATED` | Token count not reported by a provider |
| `fixture` / `fixture_synthetic` | Web evidence read from `demos/stale_fixtures/*.json`. Never a live retrieval |
| `installed_source` | **Real** inspection of the packages installed in a demo workspace (pydantic 2.9.2, pytest 9.2.0, zod 3.23.8, vitest 2.1.9, typescript 5.9.3) |

## One command
```bash
scripts/setup.sh            # once
scripts/demo.sh offline     # A, B, D, E and the MOCK benchmark, each checked: OK / UNEXPECTED (exit code 1 on any UNEXPECTED)
```

## Individual demos
| Command | Shows |
|---|---|
| `scripts/demo.sh a` | Python pre-flight. The planner (MOCK) proposes `Field(regex=)`, `@validator`, `.dict()`. The installed pydantic 2.9.2 source flags them (INCOMPATIBLE / DEPRECATED). The briefing goes to the coder, tests run in the sandbox, and the run passes first time |
| `scripts/demo.sh b` | TypeScript pre-flight with the real TypeScript compiler API: `ZodString.nonempty` is DEPRECATED and `ZodString.min("3")` is INCOMPATIBLE (TS2345) |
| `scripts/demo.sh d` | Stale-answer detection over a 6-claim answer using fixture evidence: contradicted version, supported past event, semantic support and negation contradiction, unverified claim, stable fact, cited corrected answer |
| `scripts/demo.sh e` | Combined workflow: claims about pydantic checked against the installed package (`installed_source`), then the same APIs caught by the pre-flight check |
| `scripts/demo.sh 3 --runs 3` | Baseline vs VeriCode benchmark: **MOCK**, estimated tokens, includes one task where VeriCode uses *more* tokens |
| `scripts/demo.sh c` | Arbitrary task: prints the exact blocker (needs a real LLM). The mock never fakes it |

## In the browser
`scripts/run.sh`, then open the printed login URL:
1. **Stale-Answer Detector**: *Load Demo 2 answer* → *Offline fixture* → *Extract & verify*. Click highlighted spans,
   expand claims (authority tier, hedging/qualifier badges, supporting vs contradicting evidence) → *Generate corrected answer*.
2. Same screen: paste a claim about pydantic, pytest, zod or vitest and pick a workspace under *Check API claims
   against installed packages*. Evidence appears as `installed_source`.
3. **Pre-Flight Inspector**: *Inspect* `sample_project` / `ts_project`, load a demo task, *Run pre-flight*, and look at the confidence heatmap.
4. **Coding Workspace**: run a Demo task (VeriCode and Baseline modes), then review the diff, sandbox test output and *Apply*.
5. **Token Analytics**: *Run benchmark*. Results appear under "Mock / estimated results", never under "Real provider results".

## What the offline demos do NOT show
No live Tavily retrieval, no real model output, no real evidence-judge verdicts, no provider-reported tokens. Those need
credentials: see the README section "After configuring API keys".
