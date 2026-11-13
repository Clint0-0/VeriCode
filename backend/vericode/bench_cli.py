"""Benchmark command line: plan (estimate) -> run (resumable, budgeted) -> report.

  python -m vericode.bench_cli --plan                                  # ESTIMATED usage per task/configuration, no LLM calls
  python -m vericode.bench_cli --runs 3 --records runs.jsonl           # run (re-running skips completed runs)
  python -m vericode.bench_cli --runs 3 --records runs.jsonl --max-tokens 150000
  python -m vericode.bench_cli --report-only --records runs.jsonl --out results/

Records (one JSON line per run) are the source of truth; summaries and reports are always recomputed from them.
Nothing printed or written contains API keys (checked before writing).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import benchmark
from .agent import CODER_SYSTEM, deps_compact, deps_summary, file_block, load_catalog, outline
from .api_risk import assess
from .config import ROOT, settings
from .llm import estimate_tokens, provider_status
from .repo_intel import conventions_text, inspect_project, select_relevant_files
from .skeleton import PLANNER_SYSTEM

# planning assumptions for the ESTIMATE only (never used as measurements)
EST_CODER_OUTPUT = 900  # visible + reasoning tokens of one coder call (gpt-oss-120b live runs: ~200-1,500)
EST_PLANNER_OUTPUT = 300
EST_REPAIR_RATE = {"baseline": 0.5, "vericode_full": 0.3, "vericode_adaptive": 0.3, "context_only": 0.5}


def estimate(task: dict, cfg: str, request_cap: int | None = None, max_tokens: int = 4000) -> dict:
    project = (ROOT / "demos" / task["project"]).resolve()
    env = inspect_project(project)
    prompt = task["prompt"]
    if cfg == "baseline":
        ctx = "\n\n".join(file_block(project, f.path) for f in env.files)
        coder_in = estimate_tokens(CODER_SYSTEM + prompt + ctx) + 30
        planner = 0
        path = "baseline"
    else:
        sel = [s["path"] for s in select_relevant_files(env, prompt)]
        ctx = "\n\n".join(file_block(project, p) for p in sel if (project / p).exists())
        path = "full" if cfg == "vericode_full" else "context_only" if cfg == "context_only" else (
            "fast" if assess(env, prompt).fast_path else "full")
        planner = (estimate_tokens(PLANNER_SYSTEM + prompt + deps_summary(env) + outline(env, sel)) + EST_PLANNER_OUTPUT) if path == "full" else 0
        extra = deps_summary(env) if cfg == "vericode_full" else deps_compact(env)
        coder_in = estimate_tokens(CODER_SYSTEM + prompt + ctx + extra + conventions_text(env)) + (150 if path == "full" else 40)
    one = coder_in + EST_CODER_OUTPUT
    total = round(planner + one * (1 + EST_REPAIR_RATE[cfg]))
    blocked = bool(request_cap) and coder_in + 64 + 512 > request_cap
    return {"task": task["id"], "configuration": cfg, "path": path, "coder_prompt_tokens": coder_in, "planner_tokens": planner,
            "estimated_total_tokens": total, "label": "ESTIMATED",
            "request_size_blocked": blocked,
            "note": (f"coder prompt ~{coder_in} tokens leaves < 512 output tokens under the {request_cap}-token per-request cap"
                     if blocked else None)}


def _secret_free(text: str) -> None:
    for k in (settings.openai_api_key, settings.anthropic_api_key, settings.tavily_api_key):
        if k and len(k) > 8 and k in text:
            raise SystemExit("refusing to write output that contains a configured API key")


def markdown(result: dict, catalog: list[dict]) -> str:
    s = result["summary"]
    L = [f"# VeriCode benchmark results ({time.strftime('%Y-%m-%d', time.gmtime(result.get('created_at', time.time())))})", "",
         f"Provider `{result.get('provider')}`, coder model `{result.get('coder_model')}`, planner model `{result.get('planner_model')}`; "
         f"{result.get('runs_per_mode')} repetition(s) per configuration; repair budget {result.get('repair_budget')}; "
         f"measurement labels present: {', '.join(result.get('measurement_labels') or ['none'])}.", ""]
    if result.get("stopped"):
        L += [f"**Batch stopped early:** {result['stopped']}. Remaining runs are recorded as BLOCKED (not run).", ""]
    L += ["## Overall (paired, successful runs only)", "", "| Configuration | Tasks compared | Pairs | Token-weighted savings | Median task savings | Tasks with negative savings | Label |",
          "|---|---|---|---|---|---|---|"]
    for cfg, o in s["overall"].items():
        L.append(f"| {cfg} | {o['tasks_compared']}/{o['tasks_total']} | {o['pairs']} | {_pct(o['token_weighted_savings_pct'])} | "
                 f"{_pct(o['median_task_savings_pct'])} | {o['tasks_with_negative_savings']} | {o['measurement'] or '-'} |")
    L += ["", "## Per task", "", "| Task | Lang | Size | Category | Configuration | Runs (done/blocked) | Success | First pass | Mean tokens (in/out) | Planner | Repairs | API problems shipped | Paired savings vs baseline |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in s["tasks"]:
        for cfg, c in t["configurations"].items():
            comp = t["comparisons"].get(cfg)
            ps = comp["paired_savings"] if comp else None
            sav = "-" if cfg == "baseline" else ("n/a" if not ps or not ps["n"] else
                                                  f"{ps['mean']}% (median {ps['median']}, n={ps['n']}, {ps['evidence']}"
                                                  + (f", 95% CI {ps['ci95'][0]}..{ps['ci95'][1]}" if ps.get("ci95") else "") + ")")
            L.append(f"| {t['task']} | {t.get('language') or ''} | {t.get('repo_size') or ''} | {t.get('category') or ''} | {cfg} | "
                     f"{c['completed']}/{c['blocked']} | {_pct(c['success_rate'], 100)} | {_pct(c['first_pass_rate'], 100)} | "
                     f"{_n(c['total_tokens']['mean'])} ({_n(c['input_tokens']['mean'])}/{_n(c['output_tokens']['mean'])}) | "
                     f"{_n(c['planner_tokens']['mean'])} | {_n(c['repair_attempts']['mean'])} | {_n(c['api_problems_shipped']['mean'])} | {sav} |")
    fails = [(t["task"], cfg, f) for t in s["tasks"] for cfg, c in t["configurations"].items() for f in c["failures"]]
    if fails:
        L += ["", "## Failed and blocked runs", "", "| Task | Configuration | Rep | Status | Detail |", "|---|---|---|---|---|"]
        for task, cfg, f in fails:
            L.append(f"| {task} | {cfg} | {f['rep']} | {f['status']} | {(f.get('error') or '').replace('|', '/')[:160]} |")
    return "\n".join(L) + "\n"


def _pct(v, scale=1):
    return "-" if v is None else f"{round(v * scale, 1)}%"


def _n(v):
    return "-" if v is None else f"{v:,.0f}" if isinstance(v, (int, float)) and abs(v) >= 10 else f"{v}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vericode.bench_cli")
    ap.add_argument("--tasks", default="", help="comma-separated catalog ids (default: all)")
    ap.add_argument("--configurations", default=",".join(benchmark.DEFAULT_CONFIGURATIONS))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--records", default="", help="JSONL of run records (appended to; completed runs are skipped)")
    ap.add_argument("--max-tokens", type=int, default=None, help="stop starting runs after this many ACTUAL tokens")
    ap.add_argument("--max-runs", type=int, default=None)
    ap.add_argument("--request-cap", type=int, default=None, help="provider per-request token cap, for --plan")
    ap.add_argument("--plan", action="store_true", help="print ESTIMATED usage only; no LLM calls")
    ap.add_argument("--report-only", action="store_true", help="summarise existing --records without running")
    ap.add_argument("--out", default="", help="directory for summary.json and report.md")
    ap.add_argument("--no-live-docs", action="store_true", help="pre-flight without Tavily documentation lookups")
    ap.add_argument("--drop", default="", help="task:configuration pairs whose earlier records are discarded before "
                                               "resuming (e.g. runs produced by code with a since-fixed defect); they are re-run")
    a = ap.parse_args(argv)
    if not 1 <= a.runs <= 10:
        ap.error("--runs must be between 1 and 10")
    ids = [x for x in a.tasks.split(",") if x]
    cfgs = tuple(x for x in a.configurations.split(",") if x)
    catalog = [t for t in load_catalog() if not ids or t["id"] in ids]
    if ids and len(catalog) != len(ids):
        ap.error(f"unknown task id(s): {sorted(set(ids) - {t['id'] for t in catalog})}")

    if a.drop and a.records and Path(a.records).exists():
        pairs = {tuple(x.split(":", 1)) for x in a.drop.split(",") if ":" in x}
        kept, dropped = [], []
        for r in benchmark.load_records(a.records):
            (dropped if (r["task"], r["configuration"]) in pairs else kept).append(r)
        Path(a.records).write_text("".join(json.dumps(r, default=str) + "\n" for r in kept))
        Path(a.records).with_suffix(".dropped.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in dropped))
        print(f"dropped {len(dropped)} earlier record(s) for {sorted(pairs)} (kept in {Path(a.records).with_suffix('.dropped.jsonl').name})")

    if a.plan:
        rows = [estimate(t, c, a.request_cap) for t in catalog for c in (("baseline",) + tuple(x for x in cfgs if x != "baseline"))]
        total = sum(r["estimated_total_tokens"] for r in rows if not r["request_size_blocked"]) * a.runs
        out = {"label": "ESTIMATED", "runs_per_configuration": a.runs, "rows": rows, "estimated_total_tokens": total,
               "assumptions": {"coder_output": EST_CODER_OUTPUT, "planner_output": EST_PLANNER_OUTPUT, "repair_rate": EST_REPAIR_RATE}}
        text = json.dumps(out, indent=2)
        _secret_free(text)
        print(text)
        return 0

    if a.report_only:
        records = benchmark.load_records(a.records)
        result = {"summary": benchmark.summarize(records, catalog), "records": records, "created_at": time.time(),
                  "measurement_labels": sorted({r["measurement"] for r in records if r.get("measurement")}),
                  **{k: v for k, v in provider_status().items() if k in ("provider", "coder_model", "planner_model")},
                  "runs_per_mode": max((r["rep"] for r in records), default=0), "repair_budget": settings.max_repair_attempts}
    else:
        result = benchmark.run_benchmark(ids or None, a.runs, live=not a.no_live_docs, configurations=cfgs, records_path=a.records or None,
                                         max_total_tokens=a.max_tokens, max_runs=a.max_runs,
                                         progress=lambda r: print(f"[run] {r['task']} rep {r['rep']} {r['configuration']}: {r['status']} "
                                                                  f"{r['total_tokens']} tokens ({r['measurement']}) path={r.get('execution_path')}", flush=True))
    report = markdown(result, catalog)
    summary = json.dumps({k: result.get(k) for k in ("id", "created_at", "provider", "coder_model", "planner_model", "runs_per_mode",
                                                     "repair_budget", "measurement_labels", "stopped", "tokens_spent_actual", "summary")},
                         indent=2, default=str)
    _secret_free(report + summary)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "summary.json").write_text(summary)
        (out / "report.md").write_text(report)
    print(report)
    print("===SUMMARY_JSON_BEGIN===")
    print(summary)
    print("===SUMMARY_JSON_END===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
