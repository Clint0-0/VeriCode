"""Reproducible hackathon demos from the command line.

    python -m vericode.demo 1          # Pre-flight API detection + implementation + tests
    python -m vericode.demo 2 [--live] # Stale-answer detection (fixture by default; --live uses Tavily)
    python -m vericode.demo 3 [--runs N]  # Baseline vs VeriCode benchmark
"""
from __future__ import annotations

import argparse
import json

from . import db, stale
from .agent import TaskRunner, create_task, load_catalog
from .benchmark import run_benchmark
from .config import ROOT, settings


def demo1(task_id: str = "users") -> None:
    from .llm import provider_status
    from .security import sandbox_backend
    t = next(x for x in load_catalog() if x["id"] == task_id)
    project = (ROOT / "demos" / t["project"]).resolve()
    ps = provider_status()
    print(f"provider={ps['provider']} (ready={ps['ready']}{', missing: ' + ', '.join(ps['missing']) if ps['missing'] else ''})  "
          f"tavily={'configured' if settings.tavily_api_key else 'NOT configured (TAVILY_API_KEY)'}  sandbox={sandbox_backend()}")
    tid = create_task(project, t["prompt"], "vericode")
    r = TaskRunner(tid, project, t["prompt"], "vericode", acceptance=t["acceptance_tests"]).run()
    pf = db.loads(db.row("SELECT preflight_json FROM tasks WHERE id=?", (tid,))["preflight_json"], {})
    print("\n== Installed dependencies ==")
    for d in pf["environment"]["dependencies"]:
        print(f"  {d['name']}: declared {d['declared']}  installed {d['installed']}")
    print("\n== Planned API skeleton ==")
    for p in pf["skeleton"]["packages"]:
        for a in p["planned_apis"]:
            print(f"  {a['import_path']}.{a['name']}({', '.join(a['arguments'])})  [plan assumed {p['assumed_version']}]")
    print("\n== Verification ==")
    for f in pf["findings"]:
        print(f"  {f['status']:<15} {f['planned_api']:<28} risk={f['risk_score']:<3} {f['explanation'][:110]}")
        if f.get("live"):
            print(f"      live: {f['live']['status']} {f['live'].get('detail', '')[:90]}")
    print("\n" + pf["briefing"])
    print("\n== Result ==")
    print(f"  outcome={r.get('outcome')} first_pass={r.get('first_pass_success')} repairs={r.get('repair_attempts')} tokens={r['tokens']['total']} ({r['tokens']['measurement']})")
    print(r.get("diff", r.get("error")))
    for c in r.get("checks", {}).get("results", []):
        print(f"  {c['command']} -> exit {c['returncode']}  ({c['isolation']})\n  {c['stdout'].strip().splitlines()[-1] if c['stdout'].strip() else ''}")
    return r


def demo2(live: bool) -> None:
    d = json.loads((ROOT / "demos" / "stale_fixtures" / "demo2.json").read_text())
    res = stale.analyze(d["answer"], mode="live" if live else "fixture")
    s = res["summary"]
    print(f"evidence mode: {s['evidence_mode']}  (tavily configured: {s['tavily_configured']}, searches {s['search_calls']}, "
          f"credits {s.get('search_credits')})  extraction: {s.get('extraction')}  judge: {s.get('llm_judge')}\n")
    for c in res["claims"]:
        cl = c["claim"]
        print(f"[{c['status']}] {cl['claim']}")
        print(f"   category={cl['category']} volatility={cl['volatility']} freshness={c['freshness']} confidence={c['confidence']}")
        print(f"   {c['explanation'][:200]}")
        if c.get("missing_evidence"):
            print(f"   missing evidence: {c['missing_evidence']}")
        for e in c["evidence"]:
            if e["outcome"] in ("support", "contradict"):
                print(f"   - {e['outcome']}: {e['url']} (published {e['published_date']}, origin {e['origin']})")
    corr = stale.corrected_answer(res["id"])
    print("\nCorrected answer:\n  " + corr["corrected"])
    for ci in corr["citations"]:
        print(f"  [{ci['n']}] {ci['url']} ({ci['origin']})")
    return res


def demo3(runs: int) -> None:
    res = run_benchmark(runs=runs)
    if res.get("average_savings_pct") is not None:
        print(f"average savings over {res['comparable_tasks']}/{res['total_tasks']} comparable tasks: {res['average_savings_pct']}%")
    print(f"provider={res['provider']} model={res.get('coder_model')} measurement={res['measurement']} runs/mode={runs} repair budget={res['repair_budget']}\n")
    for t in res["tasks"]:
        b, v = t["summary"]["baseline"], t["summary"]["vericode"]
        print(t["title"])
        print(f"  baseline : tokens {b['total_tokens']['mean']} ± {b['total_tokens']['stdev']}  success {b['success_rate']:.0%}  first-pass {b['first_pass_rate']:.0%}  repairs {b['repair_attempts']['mean']}  calls {b['llm_calls']['mean']}")
        print(f"  vericode : tokens {v['total_tokens']['mean']} ± {v['total_tokens']['stdev']}  success {v['success_rate']:.0%}  first-pass {v['first_pass_rate']:.0%}  repairs {v['repair_attempts']['mean']}  calls {v['llm_calls']['mean']}")
        print(f"  savings  : {t['token_savings_pct']}%" if t["savings_valid"] else f"  savings  : n/a - {t['savings_note']}")
        print(f"  verification overhead (vericode): {v['verification_overhead_tokens']['mean']} tokens")
        if t["detection"]["detection_rate"] is not None:
            print(f"  detection rate {t['detection']['detection_rate']}, false-positive rate {t['detection']['false_positive_rate']}")
    return res


ARBITRARY_TASK = ("Add a method due_within(self, now, days) to TaskStore in taskboard/storage.py that returns open tasks whose due "
                  "date falls within the next `days` days (inclusive), sorted by due date, and add pytest tests for it in tests/test_due_within.py.")


def demoC() -> None:
    """Arbitrary (non-bundled) coding task. Needs a real LLM provider; the MOCK provider refuses it explicitly."""
    from .llm import LLMUnavailable, provider_status
    ps = provider_status()
    project = (ROOT / "demos" / "sample_project").resolve()
    print(f"task: {ARBITRARY_TASK}\nprovider: {ps['provider']} (real={ps['real']}, ready={ps['ready']})")
    if not (ps["real"] and ps["ready"]):
        print("BLOCKED: an arbitrary task needs a real LLM provider. Set ANTHROPIC_API_KEY or OPENAI_API_KEY and VERICODE_CODER_MODEL.")
        try:
            r = TaskRunner(create_task(project, ARBITRARY_TASK, "vericode"), project, ARBITRARY_TASK, "vericode").run()
            print(f"mock attempt -> outcome={r.get('outcome')} error={r.get('error')}")
        except LLMUnavailable as e:
            print(f"mock attempt -> {e}")
        return
    for mode in ("baseline", "vericode"):
        r = TaskRunner(create_task(project, ARBITRARY_TASK, mode), project, ARBITRARY_TASK, mode).run()
        print(f"{mode}: outcome={r.get('outcome')} first_pass={r.get('first_pass_success')} repairs={r.get('repair_attempts')} "
              f"tokens={r['tokens']['total']} ({r['tokens']['measurement']}) files={r.get('changed_files')}")
        if r.get("error"):
            print("  error:", r["error"])


def demoE() -> None:
    """Combined workflow: an LLM answer about a library is verified (Track 1) against the INSTALLED package, and the
    same knowledge drives the pre-flight briefing for code generation (Track 2)."""
    answer = ("To validate fields in Pydantic, use the @validator decorator. Pydantic provides BaseModel.model_dump() for "
              "serialization. You can import the pydantic BaseSettings class directly from pydantic.")
    res = stale.analyze(answer, mode="fixture", workspace="sample_project")
    print("Track 1 - answer about pydantic checked against demos/sample_project (pydantic 2.9.2 installed):")
    for c in res["claims"]:
        ev = next((e for e in c["evidence"] if e["origin"] == "installed_source"), None)
        print(f"  [{c['status']}] {c['claim']['claim']}")
        if ev:
            print(f"      installed_source: {ev['excerpt'][:150]}")
    print("\nTrack 2 - the same APIs in a coding task are caught before generation:")
    r = demo1("users")
    return res, r


def offline_suite(runs: int = 1) -> None:
    """Every demo that works without credentials. Labels: MOCK (scripted coder), ESTIMATED tokens, FIXTURE evidence,
    installed_source evidence. Nothing here is a live result."""
    from .config import settings as s
    s.llm_provider = "mock"
    print("=" * 78)
    print("VeriCode OFFLINE demo suite - no API keys used.")
    print("LLM = MOCK (scripted, tokens estimated chars/4) | web evidence = FIXTURE files | installed_source = real local packages")
    print("=" * 78)
    ok_task = lambda r: r.get("outcome") == "succeeded" and r.get("first_pass_success")  # noqa: E731
    steps = [("A - Python pre-flight (pydantic 2.9.2)", lambda: demo1("users"), ok_task),
             ("B - TypeScript pre-flight (zod 3.23.8, TypeScript compiler API)", lambda: demo1("signup"), ok_task),
             ("D - Stale-answer detection (FIXTURE evidence)", lambda: demo2(False),
              lambda res: [c["status"] for c in res["claims"]] == ["CONTRADICTED", "CURRENT_SUPPORTED", "CURRENT_SUPPORTED",
                                                                    "CONTRADICTED", "UNVERIFIED", "NOT_APPLICABLE"]),
             ("E - Combined workflow (installed_source evidence)", demoE,
              lambda x: [c["status"] for c in x[0]["claims"]] == ["CONTRADICTED", "CURRENT_SUPPORTED", "CONTRADICTED"] and ok_task(x[1])),
             ("3 - Baseline vs VeriCode benchmark (MOCK)", lambda: demo3(runs),
              lambda res: res["measurement"] == "MOCK" and all(t["savings_valid"] for t in res["tasks"]))]
    results = []
    for title, fn, check in steps:
        print("\n" + "#" * 20, title, "#" * 20)
        try:
            out = fn()
            results.append((title, "OK" if check(out) else "UNEXPECTED"))
        except Exception as e:  # report and continue
            results.append((title, f"FAILED: {type(e).__name__}: {e}"))
            print("FAILED:", e)
    print("\n" + "=" * 78 + "\nOffline suite summary (labels: MOCK / ESTIMATED / FIXTURE / installed_source):")
    for t, r in results:
        print(f"  {r:<10} {t}")
    if any(r != "OK" for _, r in results):
        raise SystemExit(1)
    print("Demo C (arbitrary task) needs a real LLM: scripts/demo.sh c after configuring ANTHROPIC_API_KEY/OPENAI_API_KEY + VERICODE_CODER_MODEL.")



def _positive_int(v: str) -> int:
    import argparse
    n = int(v)
    if not 1 <= n <= 10:
        raise argparse.ArgumentTypeError("--runs must be between 1 and 10")
    return n

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("demo", choices=["1", "1b", "2", "3", "a", "b", "c", "d", "e", "all", "offline"])
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--runs", type=_positive_int, default=1)
    a = ap.parse_args()
    db.init_db()
    a.demo = {"a": "1", "b": "1b", "d": "2"}.get(a.demo, a.demo)
    if a.demo == "offline":
        offline_suite(a.runs)
        return
    if a.demo == "c":
        print("#" * 20, "DEMO C - ARBITRARY CODING TASK", "#" * 20)
        demoC()
        return
    if a.demo == "e":
        print("#" * 20, "DEMO E - COMBINED WORKFLOW", "#" * 20)
        demoE()
        return
    if a.demo in ("1", "all"):
        print("#" * 20, "DEMO 1 - PRE-FLIGHT API DETECTION", "#" * 20)
        demo1()
    if a.demo in ("1b", "all"):
        print("\n" + "#" * 20, "DEMO 1b - TYPESCRIPT PRE-FLIGHT (zod)", "#" * 20)
        demo1("signup")
    if a.demo in ("2", "all"):
        print("\n" + "#" * 20, "DEMO 2 - STALE-ANSWER DETECTION", "#" * 20)
        demo2(a.live)
    if a.demo == "all":
        print("\n" + "#" * 20, "DEMO E - COMBINED WORKFLOW", "#" * 20)
        demoE()
        print("\n" + "#" * 20, "DEMO C - ARBITRARY CODING TASK", "#" * 20)
        demoC()
    if a.demo in ("3", "all"):
        print("\n" + "#" * 20, "DEMO 3 - TOKEN-EFFICIENT AGENT vs BASELINE", "#" * 20)
        demo3(a.runs)


if __name__ == "__main__":
    main()
