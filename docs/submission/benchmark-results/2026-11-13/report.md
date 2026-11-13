# VeriCode benchmark results (2026-11-13)

Provider `openai`, coder model `openai/gpt-oss-120b`, planner model `openai/gpt-oss-120b`; 3 repetition(s) per configuration; repair budget 3; measurement labels present: ACTUAL_PROVIDER_USAGE.

## Overall (paired, successful runs only)

| Configuration | Tasks compared | Pairs | Token-weighted savings | Median task savings | Tasks with negative savings | Label |
|---|---|---|---|---|---|---|
| vericode_adaptive | 5/12 | 12 | 46.0% | 45.6% | 1 | ACTUAL_PROVIDER_USAGE |
| vericode_full | 6/12 | 15 | 28.7% | 36.1% | 1 | ACTUAL_PROVIDER_USAGE |

## Per task

| Task | Lang | Size | Category | Configuration | Runs (done/blocked) | Success | First pass | Mean tokens (in/out) | Planner | Repairs | API problems shipped | Paired savings vs baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| summary | python | small | feature | baseline | 3/0 | 100.0% | 33.3% | 4,959 (4,375/584) | 0 | 0.7 | 0 | - |
| summary | python | small | feature | vericode_full | 3/0 | 100.0% | 100.0% | 2,428 (1,674/754) | 1,092 | 0 | 0 | 40.9% (median 62.7, n=3, exploratory) |
| summary | python | small | feature | vericode_adaptive | 3/0 | 100.0% | 100.0% | 1,250 (909/341) | 0 | 0 | 0 | 71.2% (median 79.0, n=3, exploratory) |
| signup | typescript | small | feature | baseline | 3/0 | 100.0% | 100.0% | 808 (560/248) | 0 | 0 | 0 | - |
| signup | typescript | small | feature | vericode_full | 3/0 | 100.0% | 100.0% | 2,475 (1,506/970) | 1,529 | 0 | 0 | -210.8% (median -158.1, n=3, exploratory) |
| signup | typescript | small | feature | vericode_adaptive | 3/0 | 100.0% | 100.0% | 2,238 (1,264/974) | 1,337 | 0 | 0 | -177.6% (median -171.9, n=3, exploratory) |
| ord_bugfix | typescript | medium | bugfix | baseline | 3/0 | 100.0% | 100.0% | 3,418 (2,806/612) | 0 | 0 | 0 | - |
| ord_bugfix | typescript | medium | bugfix | vericode_full | 3/0 | 100.0% | 100.0% | 3,257 (2,041/1,216) | 1,326 | 0 | 0 | 4.7% (median 5.4, n=3, exploratory) |
| ord_bugfix | typescript | medium | bugfix | vericode_adaptive | 3/0 | 66.7% | 66.7% | 3,337 (1,629/1,708) | 0 | 1 | 0 | 45.6% (median 45.6, n=2, anecdotal) |
| inv_restock | python | medium | feature | baseline | 3/0 | 100.0% | 0.0% | 9,291 (6,794/2,497) | 0 | 1 | - | - |
| inv_restock | python | medium | feature | vericode_full | 3/0 | 66.7% | 66.7% | 7,364 (4,401/2,963) | 1,529 | 1 | - | 47.3% (median 47.3, n=2, anecdotal) |
| inv_restock | python | medium | feature | vericode_adaptive | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| inv_refactor | python | medium | refactor | baseline | 3/0 | 100.0% | 100.0% | 4,152 (3,179/973) | 0 | 0 | 0 | - |
| inv_refactor | python | medium | refactor | vericode_full | 3/0 | 100.0% | 100.0% | 3,113 (1,474/1,639) | 684 | 0 | 0 | 24.6% (median 21.3, n=3, exploratory) |
| inv_refactor | python | medium | refactor | vericode_adaptive | 3/0 | 100.0% | 100.0% | 2,458 (868/1,590) | 0 | 0 | 0 | 40.9% (median 39.3, n=3, exploratory) |
| users | python | small | feature | baseline | 1/2 | 100.0% | 0.0% | 6,840 (5,733/1,107) | 0 | 1 | 0 | - |
| users | python | small | feature | vericode_full | 1/2 | 100.0% | 0.0% | 3,103 (1,949/1,154) | 931 | 1 | 0 | 54.6% (median 54.6, n=1, anecdotal) |
| users | python | small | feature | vericode_adaptive | 1/2 | 100.0% | 100.0% | 1,911 (1,054/857) | 950 | 0 | 0 | 72.1% (median 72.1, n=1, anecdotal) |
| ord_schema | typescript | medium | feature | baseline | 0/3 | - | - | - (-/-) | - | - | - | - |
| ord_schema | typescript | medium | feature | vericode_full | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| ord_schema | typescript | medium | feature | vericode_adaptive | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| ord_modify | typescript | medium | modification | baseline | 0/3 | - | - | - (-/-) | - | - | - | - |
| ord_modify | typescript | medium | modification | vericode_full | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| ord_modify | typescript | medium | modification | vericode_adaptive | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| inv_tests | python | medium | tests | baseline | 0/3 | - | - | - (-/-) | - | - | - | - |
| inv_tests | python | medium | tests | vericode_full | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| inv_tests | python | medium | tests | vericode_adaptive | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| led_fx_bugfix | python | large | bugfix | baseline | 0/3 | - | - | - (-/-) | - | - | - | - |
| led_fx_bugfix | python | large | bugfix | vericode_full | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| led_fx_bugfix | python | large | bugfix | vericode_adaptive | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| led_export | python | large | feature | baseline | 0/3 | - | - | - (-/-) | - | - | - | - |
| led_export | python | large | feature | vericode_full | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| led_export | python | large | feature | vericode_adaptive | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| led_cashflow | python | large | feature | baseline | 0/3 | - | - | - (-/-) | - | - | - | - |
| led_cashflow | python | large | feature | vericode_full | 0/3 | - | - | - (-/-) | - | - | - | n/a |
| led_cashflow | python | large | feature | vericode_adaptive | 0/3 | - | - | - (-/-) | - | - | - | n/a |

## Failed and blocked runs

| Task | Configuration | Rep | Status | Detail |
|---|---|---|---|---|
| ord_bugfix | vericode_adaptive | 3 | FAILED | checks still failing after 3 repair attempt(s) |
| inv_restock | vericode_full | 2 | FAILED | checks still failing after 3 repair attempt(s) |
| users | vericode_full | 2 | BLOCKED | LLMUnavailable: openai: rate limited (HTTP 429) after retries; provider asks to retry after 382s; limits {'x-ratelimit-limit-requests': '1000', 'x-ratelimit-remaining-requests': '906', 'x-ratelimit-re |

## Not run (budget or provider stop; recorded as BLOCKED, re-run on resume)

inv_restock: 3, users: 5, ord_schema: 9, ord_modify: 9, inv_tests: 9, led_fx_bugfix: 9, led_export: 9, led_cashflow: 9. Reason: not run: provider blocked a run.
