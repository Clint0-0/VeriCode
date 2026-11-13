"""Module M - baseline vs VeriCode benchmark (configurations, paired runs, resumable batches).

Fairness: every configuration of a task gets the same provider/model/settings, task prompt, pristine copy of
the same repository snapshot (content fingerprint recorded per run), the same seeded setup files and acceptance
tests, the same validation commands, the same repair budget and the same command timeouts. Repetitions are
interleaved (rep 1 of every configuration, then rep 2, ...) and the configuration order rotates per repetition so
neither side systematically runs first against a warming cache or a draining rate-limit window.

Measurement: ALL LLM calls are counted (planner + coder + repairs). Each run is labelled
ACTUAL_PROVIDER_USAGE / ESTIMATED / MOCK from the provider's own usage fields; labels are never mixed in one
figure. Tavily usage is reported separately as search calls (no token cost is invented for it).

Comparison: a paired saving is computed for repetition i only when BOTH the configuration's run i and the
baseline's run i succeeded and carry the same measurement label. Failed or blocked runs never produce a saving;
they are reported as success rates and failure details. Negative savings are kept.

Statuses: SUCCESS (acceptance + project tests passed), FAILED (ran, did not pass), BLOCKED (provider rate limit,
provider request-size limit, provider unavailable, or the batch's token/run budget was exhausted before the run).
"""
from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path

from . import db
from .agent import TaskRunner, create_task, load_catalog
from .config import ROOT, settings
from .repo_intel import fingerprint

PROBLEM = {"NOT_FOUND", "INCOMPATIBLE", "DEPRECATED"}
CONFIGURATIONS = ("baseline", "vericode_full", "vericode_adaptive", "context_only")
DEFAULT_CONFIGURATIONS = ("baseline", "vericode_full", "vericode_adaptive")
BLOCK_MARKERS = ("HTTP 429", "rate limited", "HTTP 413", "Request too large", "rate_limit", "No LLM provider configured",
                 "No model configured", "not ready")
# t critical values (two-sided 95%) for small samples; df >= 30 uses 2.042 -> 1.96 asymptotically
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
       11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
       25: 2.060, 29: 2.045}


# ------------------------------------------------------------------------------------------- statistics
def _stats(xs: list[float]) -> dict:
    if not xs:
        return {"mean": None, "median": None, "stdev": None, "min": None, "max": None, "n": 0}
    return {"mean": round(statistics.mean(xs), 1), "median": round(statistics.median(xs), 1),
            "stdev": round(statistics.stdev(xs), 1) if len(xs) > 1 else 0.0,
            "min": min(xs), "max": max(xs), "n": len(xs)}


def _t95(df: int) -> float:
    if df in T95:
        return T95[df]
    keys = sorted(k for k in T95 if k <= df)
    return T95[keys[-1]] if df < 30 else 1.96


def paired_stats(xs: list[float]) -> dict:
    """Mean/median/stdev of paired savings; a 95% t-interval only from n >= 5, flagged exploratory below n = 10."""
    s = _stats(xs)
    n = len(xs)
    s["ci95"] = None
    if n >= 5:
        half = _t95(n - 1) * statistics.stdev(xs) / math.sqrt(n)
        s["ci95"] = [round(s["mean"] - half, 1), round(s["mean"] + half, 1)]
    s["evidence"] = "none" if n == 0 else "anecdotal" if n < 3 else "exploratory" if n < 10 else "moderate"
    return s


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


def classify(result: dict) -> str:
    if result.get("success"):
        return "SUCCESS"
    err = result.get("error") or ""
    if any(m in err for m in BLOCK_MARKERS):
        return "BLOCKED"
    return "FAILED"


def stage_tokens(by_stage: dict, stages: tuple[str, ...]) -> int:
    return sum(v["input"] + v["output"] for k, v in (by_stage or {}).items() if k in stages)


def make_record(task: dict, rep: int, config: str, result: dict, task_id: str | None, snapshot: str) -> dict:
    tok = result.get("tokens") or {"input": 0, "output": 0, "total": 0, "calls": 0, "by_stage": {}, "measurement": "MOCK"}
    by = tok.get("by_stage") or {}
    return {
        "task": task["id"], "rep": rep, "configuration": config, "task_id": task_id, "status": classify(result),
        "success": bool(result.get("success")), "first_pass_success": bool(result.get("first_pass_success")),
        "repair_attempts": result.get("repair_attempts", 0), "test_pass_rate": result.get("test_pass_rate"),
        "execution_path": result.get("execution_path"), "risk": (result.get("risk") or {}).get("risk"),
        "measurement": tok.get("measurement"), "input_tokens": tok.get("input", 0), "output_tokens": tok.get("output", 0),
        "total_tokens": tok.get("total", 0), "llm_calls": tok.get("calls", 0), "by_stage": by,
        "planner_tokens": stage_tokens(by, ("planner",)), "coder_tokens": stage_tokens(by, ("coder",)),
        "repair_tokens": stage_tokens(by, ("repair",)),
        "search_calls": result.get("search_calls", 0), "duration_s": result.get("duration_s"),
        "timings_s": result.get("timings_s") or {},
        "api_problems_shipped": (result.get("api_audit") or {}).get("problem_count"),
        "api_problems_detail": [f"{p.get('planned_api')} [{p.get('status')}]" for p in (result.get("api_audit") or {}).get("problems", [])][:8],
        "preflight_findings": result.get("_preflight_findings"),
        "error": (result.get("error") or "")[:400] or None, "snapshot": snapshot,
        "provider": result.get("provider"), "finished_at": time.time(),
    }


def blocked_record(task: dict, rep: int, config: str, reason: str, snapshot: str) -> dict:
    return {"task": task["id"], "rep": rep, "configuration": config, "task_id": None, "status": "BLOCKED", "success": False,
            "first_pass_success": False, "repair_attempts": 0, "measurement": None, "input_tokens": 0, "output_tokens": 0,
            "total_tokens": 0, "llm_calls": 0, "by_stage": {}, "error": reason, "snapshot": snapshot, "not_run": True,
            "finished_at": time.time()}


def summarize(records: list[dict], catalog: list[dict] | None = None, baseline: str = "baseline") -> dict:
    """Pure aggregation over run records (testable, used by the API, the live harness and the report)."""
    meta = {t["id"]: t for t in (catalog or [])}
    tasks: dict[str, dict] = {}
    for r in records:
        tasks.setdefault(r["task"], {}).setdefault(r["configuration"], []).append(r)
    out_tasks = []
    for tid, by_cfg in tasks.items():
        cfgs = {}
        for cfg, rs in by_cfg.items():
            ran = [r for r in rs if r["status"] != "BLOCKED"]
            ok = [r for r in ran if r["status"] == "SUCCESS"]
            labels = sorted({r["measurement"] for r in ran if r.get("measurement")})
            cfgs[cfg] = {
                "runs": len(rs), "completed": len(ran), "blocked": len(rs) - len(ran),
                "success_rate": round(len(ok) / len(ran), 3) if ran else None,
                "first_pass_rate": round(sum(r["first_pass_success"] for r in ran) / len(ran), 3) if ran else None,
                "measurement": labels[0] if len(labels) == 1 else ("MIXED" if labels else None),
                "total_tokens": _stats([r["total_tokens"] for r in ran]),
                "total_tokens_successful": _stats([r["total_tokens"] for r in ok]),
                "input_tokens": _stats([r["input_tokens"] for r in ran]),
                "output_tokens": _stats([r["output_tokens"] for r in ran]),
                "planner_tokens": _stats([r.get("planner_tokens", 0) for r in ran]),
                "coder_tokens": _stats([r.get("coder_tokens", 0) for r in ran]),
                "repair_tokens": _stats([r.get("repair_tokens", 0) for r in ran]),
                "llm_calls": _stats([r["llm_calls"] for r in ran]),
                "repair_attempts": _stats([r["repair_attempts"] for r in ran]),
                "duration_s": _stats([r["duration_s"] for r in ran if r.get("duration_s") is not None]),
                "test_pass_rate": _stats([r["test_pass_rate"] for r in ran if r.get("test_pass_rate") is not None]),
                "api_problems_shipped": _stats([r["api_problems_shipped"] for r in ran if r.get("api_problems_shipped") is not None]),
                "api_problems_detail": sorted({d for r in ran for d in (r.get("api_problems_detail") or [])}),
                "execution_paths": {p: sum(1 for r in ran if r.get("execution_path") == p) for p in {r.get("execution_path") for r in ran} if p},
                "failures": [{"rep": r["rep"], "status": r["status"], "error": r.get("error")} for r in rs if r["status"] != "SUCCESS"],
                "task_ids": [r.get("task_id") for r in rs],
            }
        comparisons = {}
        base = {r["rep"]: r for r in by_cfg.get(baseline, [])}
        for cfg, rs in by_cfg.items():
            if cfg == baseline:
                continue
            pairs, excluded = [], []
            for r in rs:
                b = base.get(r["rep"])
                why = None
                if b is None:
                    why = "no baseline run for this repetition"
                elif b["status"] != "SUCCESS" or r["status"] != "SUCCESS":
                    why = f"baseline {b['status']}, {cfg} {r['status']}"
                elif b.get("measurement") != r.get("measurement"):
                    why = f"measurement mismatch ({b.get('measurement')} vs {r.get('measurement')})"
                elif not b["total_tokens"]:
                    why = "baseline used 0 tokens"
                if why:
                    excluded.append({"rep": r["rep"], "reason": why})
                    continue
                pairs.append({"rep": r["rep"], "baseline": b["total_tokens"], "configuration": r["total_tokens"],
                              "savings_pct": round((b["total_tokens"] - r["total_tokens"]) / b["total_tokens"] * 100, 1),
                              "measurement": r["measurement"]})
            sav = [p["savings_pct"] for p in pairs]
            bsum, csum = sum(p["baseline"] for p in pairs), sum(p["configuration"] for p in pairs)
            comparisons[cfg] = {"pairs": pairs, "excluded": excluded, "paired_savings": paired_stats(sav),
                                "mean_token_savings_pct": round((bsum - csum) / bsum * 100, 1) if pairs and bsum else None,
                                "measurement": pairs[0]["measurement"] if pairs else None}
        m = meta.get(tid, {})
        out_tasks.append({"task": tid, "title": m.get("title", tid), "language": m.get("language"),
                          "repo_size": m.get("repo_size"), "category": m.get("category"), "api_risk": m.get("api_risk"),
                          "configurations": cfgs, "comparisons": comparisons})
    overall = {}
    all_cfgs = sorted({c for t in out_tasks for c in t["comparisons"]})
    for cfg in all_cfgs:
        per = [t["comparisons"][cfg] for t in out_tasks if cfg in t["comparisons"]]
        pairs = [p for c in per for p in c["pairs"]]
        bsum, csum = sum(p["baseline"] for p in pairs), sum(p["configuration"] for p in pairs)
        task_means = [c["mean_token_savings_pct"] for c in per if c["mean_token_savings_pct"] is not None]
        labels = sorted({p["measurement"] for p in pairs})
        overall[cfg] = {"tasks_compared": len(task_means), "tasks_total": len(per), "pairs": len(pairs),
                        "token_weighted_savings_pct": round((bsum - csum) / bsum * 100, 1) if pairs and bsum else None,
                        "median_task_savings_pct": round(statistics.median(task_means), 1) if task_means else None,
                        "tasks_with_negative_savings": sum(1 for x in task_means if x < 0),
                        "measurement": labels[0] if len(labels) == 1 else ("MIXED" if labels else None)}
    return {"tasks": out_tasks, "overall": overall}


# ------------------------------------------------------------------------------------------- execution
def load_records(path: str | Path | None) -> list[dict]:
    if not path or not Path(path).exists():
        return []
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _append(path: str | Path | None, rec: dict) -> None:
    if path:
        with open(path, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")


def plan_runs(catalog: list[dict], runs: int, configurations: tuple[str, ...], done: set[tuple]) -> list[tuple[dict, int, str]]:
    """Interleaved order; configuration order rotates per repetition. Completed (non-blocked) runs are skipped."""
    order = []
    for t in catalog:
        for rep in range(1, runs + 1):
            k = (rep - 1) % len(configurations)
            for cfg in configurations[k:] + configurations[:k]:
                if (t["id"], rep, cfg) not in done:
                    order.append((t, rep, cfg))
    return order


def run_benchmark(task_ids: list[str] | None = None, runs: int = 1, max_repairs: int | None = None, live: bool = True,
                  configurations: list[str] | tuple[str, ...] | None = None, records_path: str | Path | None = None,
                  max_total_tokens: int | None = None, max_runs: int | None = None, stop_on_block: bool = True,
                  progress=None) -> dict:
    catalog = [t for t in load_catalog() if not task_ids or t["id"] in task_ids]
    cfgs = tuple(configurations or DEFAULT_CONFIGURATIONS)
    unknown = [c for c in cfgs if c not in CONFIGURATIONS]
    if unknown:
        raise ValueError(f"unknown configuration(s) {unknown}; expected {CONFIGURATIONS}")
    if "baseline" not in cfgs:
        cfgs = ("baseline",) + cfgs
    bid = db.new_id("bench_")
    repairs = settings.max_repair_attempts if max_repairs is None else max_repairs
    prior = [r for r in load_records(records_path) if r.get("configuration") in cfgs and r["task"] in {t["id"] for t in catalog}]
    done = {(r["task"], r["rep"], r["configuration"]) for r in prior if r["status"] != "BLOCKED"}
    records = [r for r in prior if r["status"] != "BLOCKED"]
    spent = sum(r["total_tokens"] for r in records if r.get("measurement") == "ACTUAL_PROVIDER_USAGE")
    snapshots = {t["id"]: fingerprint((ROOT / "demos" / t["project"]).resolve()) for t in catalog}
    det: dict[str, dict] = {}
    stop_reason = None
    executed = 0
    for t, rep, cfg in plan_runs(catalog, runs, cfgs, done):
        if stop_reason is None and max_total_tokens is not None and spent >= max_total_tokens:
            stop_reason = f"token budget exhausted ({spent} >= {max_total_tokens} actual tokens)"
        if stop_reason is None and max_runs is not None and executed >= max_runs:
            stop_reason = f"run budget exhausted ({executed} runs)"
        if stop_reason:
            rec = blocked_record(t, rep, cfg, f"not run: {stop_reason}", snapshots[t["id"]])
            records.append(rec)
            _append(records_path, rec)
            continue
        project = (ROOT / "demos" / t["project"]).resolve()
        tid = create_task(project, t["prompt"], cfg, benchmark_id=bid)
        res = TaskRunner(tid, project, t["prompt"], cfg, repairs, live=live, acceptance=t.get("acceptance_tests"),
                         seed=t.get("seed_files")).run()
        executed += 1
        if t.get("expected_findings") and res.get("execution_path") == "full":
            pf = db.loads((db.row("SELECT preflight_json FROM tasks WHERE id=?", (tid,)) or {}).get("preflight_json"), {})
            d = det.setdefault(f"{t['id']}|{cfg}", {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
            for k, v in detection_metrics(pf, t["expected_findings"]).items():
                d[k] += v
        rec = make_record(t, rep, cfg, res, tid, snapshots[t["id"]])
        records.append(rec)
        _append(records_path, rec)
        if rec.get("measurement") == "ACTUAL_PROVIDER_USAGE":
            spent += rec["total_tokens"]
        if progress:
            progress(rec)
        if rec["status"] == "BLOCKED" and stop_on_block:
            stop_reason = f"provider blocked a run ({(rec.get('error') or '')[:160]})"

    summary = summarize(records, catalog)
    for task in summary["tasks"]:
        for cfg in task["configurations"]:
            d = det.get(f"{task['task']}|{cfg}")
            if d:
                task["configurations"][cfg]["detection"] = {**d, "detection_rate": round(d["tp"] / (d["tp"] + d["fn"]), 2) if d["tp"] + d["fn"] else None,
                                                            "false_positive_rate": round(d["fp"] / (d["fp"] + d["tn"]), 2) if d["fp"] + d["tn"] else None}
    primary = next((c for c in ("vericode_adaptive", "vericode_full", "context_only") if c in cfgs), None)
    legacy = [_legacy_task(t, primary) for t in summary["tasks"]]
    labels = {r["measurement"] for r in records if r.get("measurement")}
    measurement = "MOCK" if "MOCK" in labels else "ESTIMATED" if "ESTIMATED" in labels else ("ACTUAL_PROVIDER_USAGE" if labels else "NONE")
    from .llm import provider_status
    ps = provider_status()
    valid = [t["token_savings_pct"] for t in legacy if t["token_savings_pct"] is not None]
    result = {"id": bid, "created_at": time.time(), "provider": ps["provider"], "coder_model": ps["coder_model"],
              "planner_model": ps["planner_model"], "runs_per_mode": runs, "repair_budget": repairs,
              "configurations": list(cfgs), "primary_configuration": primary, "tasks": legacy,
              "summary": summary, "records": records, "stopped": stop_reason, "tokens_spent_actual": spent,
              "measurement": measurement, "measurement_labels": sorted(labels),
              "average_savings_pct": round(statistics.mean(valid), 1) if valid else None,
              "savings_stdev_across_tasks": round(statistics.stdev(valid), 1) if len(valid) > 1 else None,
              "comparable_tasks": len(valid), "total_tasks": len(legacy), "methodology": __doc__}
    with db.tx() as c:
        c.execute("INSERT INTO benchmarks(id,created_at,task_prompt,project_path,runs,result_json,measurement) VALUES(?,?,?,?,?,?,?)",
                  (bid, result["created_at"], ",".join(t["id"] for t in catalog), "demos", runs, db.dumps(result), measurement))
    return result


def _legacy_task(t: dict, primary: str | None) -> dict:
    """Shape kept for the existing dashboard (summary.baseline / summary.vericode, token_savings_pct ...)."""
    def legacy_cfg(c: dict | None) -> dict:
        c = c or {}
        return {"runs": c.get("runs", 0), "success_rate": c.get("success_rate") or 0.0, "first_pass_rate": c.get("first_pass_rate") or 0.0,
                "total_tokens": c.get("total_tokens") or _stats([]), "input_tokens": c.get("input_tokens") or _stats([]),
                "output_tokens": c.get("output_tokens") or _stats([]), "llm_calls": c.get("llm_calls") or _stats([]),
                "repair_attempts": c.get("repair_attempts") or _stats([]),
                "verification_overhead_tokens": c.get("planner_tokens") or _stats([]),
                "duration_s": c.get("duration_s") or _stats([]), "measurement": c.get("measurement"),
                "task_ids": c.get("task_ids", []), "errors": [f["error"] for f in c.get("failures", []) if f.get("error")]}
    cfgs = t["configurations"]
    comp = t["comparisons"].get(primary) if primary else None
    b, v = cfgs.get("baseline", {}), cfgs.get(primary, {}) if primary else {}
    all_ok = bool(b) and bool(v) and b.get("success_rate") == 1 and v.get("success_rate") == 1 and not b.get("blocked") and not v.get("blocked")
    shipped = [{"baseline_flagged_apis_used": (b.get("api_problems_shipped") or {}).get("mean"),
                "vericode_flagged_apis_used": (v.get("api_problems_shipped") or {}).get("mean"),
                "baseline_details": [{"planned_api": d, "result": "still_used"} for d in b.get("api_problems_detail", [])]}]
    det = v.get("detection") or {}
    return {"task": t["task"], "title": t["title"], "summary": {"baseline": legacy_cfg(b), "vericode": legacy_cfg(v)},
            "token_savings_pct": comp["mean_token_savings_pct"] if comp and all_ok else None, "savings_valid": all_ok,
            "paired_run_savings_pct": [p["savings_pct"] for p in (comp or {}).get("pairs", [])],
            "flagged_api_usage": shipped,
            "savings_note": None if all_ok else "Not computed: at least one run failed or was blocked; comparing failed and successful runs would be unfair. Paired savings cover only repetitions where both runs succeeded.",
            "detection": {**{k: det.get(k, 0) for k in ("tp", "fp", "fn", "tn")}, "detection_rate": det.get("detection_rate"),
                          "false_positive_rate": det.get("false_positive_rate"), "flagged": det.get("tp", 0) + det.get("fp", 0)},
            "language": t.get("language"), "repo_size": t.get("repo_size"), "category": t.get("category")}
