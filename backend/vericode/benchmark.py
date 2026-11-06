"""Module M - baseline vs VeriCode benchmark.

Both modes use the same provider/model, task prompt, pristine repository copy, acceptance tests,
validation commands and repair budget. ALL LLM calls are counted (planner + coder + repairs).
Tavily usage is reported separately as search calls (no token cost is invented for it).
Savings are computed per task only when BOTH modes succeeded in every run compared.
"""
from __future__ import annotations

import statistics
import time
from pathlib import Path

from . import db
from .agent import TaskRunner, create_task, load_catalog
from .config import ROOT, settings

PROBLEM = {"NOT_FOUND", "INCOMPATIBLE", "DEPRECATED"}


def _stats(xs: list[float]) -> dict:
    if not xs:
        return {"mean": None, "stdev": None, "min": None, "max": None, "n": 0}
    return {"mean": round(statistics.mean(xs), 1), "stdev": round(statistics.stdev(xs), 1) if len(xs) > 1 else 0.0,
            "min": min(xs), "max": max(xs), "n": len(xs)}


def detection_metrics(preflight: dict, expected: dict) -> dict:
    tp = fp = fn = tn = 0
    for f in preflight.get("findings", []):
        exp = expected.get(f["planned_api"])
        if exp is None:
            continue
        flagged = f["status"] in PROBLEM
        if exp == "problem":
            tp += flagged
            fn += not flagged
        else:
            fp += flagged
            tn += not flagged
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def run_benchmark(task_ids: list[str] | None = None, runs: int = 1, max_repairs: int | None = None, live: bool = True) -> dict:
    catalog = [t for t in load_catalog() if not task_ids or t["id"] in task_ids]
    bid = db.new_id("bench_")
    repairs = settings.max_repair_attempts if max_repairs is None else max_repairs
    per_task = []
    for t in catalog:
        project = (ROOT / "demos" / t["project"]).resolve()
        modes: dict[str, list[dict]] = {"baseline": [], "vericode": []}
        det = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for i in range(runs):
            for mode in ("baseline", "vericode"):
                tid = create_task(project, t["prompt"], mode, benchmark_id=bid)
                r = TaskRunner(tid, project, t["prompt"], mode, repairs, live=live, acceptance=t.get("acceptance_tests")).run()
                r["task_id"] = tid
                modes[mode].append(r)
                if mode == "vericode" and t.get("expected_findings"):
                    pf = db.loads(db.row("SELECT preflight_json FROM tasks WHERE id=?", (tid,))["preflight_json"], {})
                    for k, v in detection_metrics(pf, t["expected_findings"]).items():
                        det[k] += v
        summary = {}
        for mode, rs in modes.items():
            summary[mode] = {
                "runs": len(rs), "success_rate": sum(bool(r.get("success")) for r in rs) / len(rs),
                "first_pass_rate": sum(bool(r.get("first_pass_success")) for r in rs) / len(rs),
                "total_tokens": _stats([r["tokens"]["total"] for r in rs]),
                "input_tokens": _stats([r["tokens"]["input"] for r in rs]),
                "output_tokens": _stats([r["tokens"]["output"] for r in rs]),
                "llm_calls": _stats([r["tokens"]["calls"] for r in rs]),
                "repair_attempts": _stats([r.get("repair_attempts", 0) for r in rs]),
                "search_calls": _stats([r.get("search_calls", 0) for r in rs]),
                "duration_s": _stats([r.get("duration_s", 0) for r in rs]),
                "by_stage": rs[-1]["tokens"]["by_stage"], "measurement": rs[-1]["tokens"]["measurement"],
                "task_ids": [r["task_id"] for r in rs], "errors": [r.get("error") for r in rs if r.get("error")],
            }
        both_ok = all(r.get("success") for r in modes["baseline"] + modes["vericode"])
        b, v = summary["baseline"]["total_tokens"]["mean"], summary["vericode"]["total_tokens"]["mean"]
        savings = round((b - v) / b * 100, 1) if both_ok and b else None
        flagged = det["tp"] + det["fp"]
        per_task.append({
            "task": t["id"], "title": t["title"], "summary": summary, "token_savings_pct": savings,
            "savings_valid": both_ok,
            "savings_note": None if both_ok else "Not computed: at least one run failed; comparing failed and successful runs would be unfair.",
            "detection": {**det, "detection_rate": round(det["tp"] / (det["tp"] + det["fn"]), 2) if det["tp"] + det["fn"] else None,
                          "false_positive_rate": round(det["fp"] / (det["fp"] + det["tn"]), 2) if det["fp"] + det["tn"] else None,
                          "flagged": flagged},
        })
    result = {"id": bid, "created_at": time.time(), "provider": settings.effective_provider(), "runs_per_mode": runs,
              "repair_budget": repairs, "tasks": per_task,
              "measurement": "estimated (mock provider, chars/4)" if settings.effective_provider() == "mock" else "provider-reported usage",
              "methodology": __doc__}
    with db.tx() as c:
        c.execute("INSERT INTO benchmarks VALUES(?,?,?,?,?,?)",
                  (bid, result["created_at"], ",".join(t["id"] for t in catalog), "demos", runs, db.dumps(result)))
    return result
