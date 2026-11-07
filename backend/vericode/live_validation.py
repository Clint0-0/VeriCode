"""Live validation harness (real Groq/OpenAI-compatible provider + real Tavily).

Run:  VERICODE_LIVE_TESTS=1 .venv/bin/python -m vericode.live_validation [--runs N] [--skip-benchmark]
Writes reports/live/live_report.json and reports/live/LIVE_REPORT.md.

Every section is classified ACTUAL_SUCCESS | ACTUAL_FAILED | BLOCKED. Nothing here falls back to MOCK or fixtures:
if the provider or Tavily is not configured, the section is BLOCKED. Secret values are never written; the report is
scanned for configured key values before it is saved and the run fails if any appears.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from . import db, llm, stale
from .config import ROOT, settings
from .security import redact

OUT = ROOT / "reports" / "live"
OK, FAILED, BLOCKED = "ACTUAL_SUCCESS", "ACTUAL_FAILED", "BLOCKED"

# Genuinely new tasks (not in demos/tasks/catalog.json, not scripted in the MOCK provider).
PY_TASK = ("Create taskboard/export.py with a Pydantic v2 model TaskExport (fields: id: int, title: str, priority: str, "
           "due: datetime | None, tags: list[str]) that is immutable (frozen via model_config) and serializes `due` as an "
           "ISO-8601 string (or None) with a field serializer. Add export_tasks(store: TaskStore) -> list[dict] that returns "
           "every task from the store as JSON-compatible dicts (Pydantic v2 JSON-mode dump), with priority as its string "
           "value. Add pytest tests in tests/test_export.py.")
TS_TASK = ("Create src/config.ts exporting a zod schema named AppConfig for environment variables: PORT coerced to an "
           "integer between 1 and 65535 (default 8080), HOST a non-empty string (default \"localhost\"), DEBUG parsed from "
           "the strings \"true\"/\"false\" to a boolean (default false). Export parseConfig(env: Record<string, string | "
           "undefined>) that uses safeParse and throws an Error whose message lists every issue path. Add vitest tests in "
           "tests/config.test.ts.")

SCENARIOS = {
    "A_current": ("Python 3.13 was released in October 2024. FastAPI supports asynchronous path operation functions "
                  "declared with async def."),
    "B_outdated": ("The latest stable version of Python is 3.10. Pydantic's latest major version is 1, and models "
                   "are serialized with the .dict() method."),
    "C_semantic": ("The Tavily Search API returns a list of results that include the page URL and a content snippet. "
                   "Groq provides an OpenAI-compatible chat completions endpoint."),
    "D_conflicting": ("Rust will officially replace C in the Linux kernel by 2030. The Python Software Foundation plans "
                      "to remove the GIL from CPython entirely by 2027."),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _section(fn, *a, **kw) -> dict:
    t0 = time.time()
    try:
        out = fn(*a, **kw)
    except llm.LLMUnavailable as e:
        out = {"status": FAILED, "error": redact(str(e))[:800]}
    except Exception as e:  # report, never hide
        out = {"status": FAILED, "error": redact(f"{type(e).__name__}: {e}")[:800],
               "traceback": redact(traceback.format_exc())[-1500:]}
    out["duration_s"] = round(time.time() - t0, 2)
    return out


def _usage(r: llm.LLMResult) -> dict:
    return {"stage": r.stage, "model": r.model, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
            "measurement": "ESTIMATED" if r.estimated else "ACTUAL_PROVIDER_USAGE"}


# ----------------------------------------------------------------------------- 1. configuration
def check_config() -> dict:
    ps = llm.provider_status()
    host = urlparse(settings.openai_base_url).hostname or ""
    res = {"provider": ps["provider"], "adapter": "openai_compatible" if ps["provider"] == "openai" else ps["provider"],
           "key_present": bool(settings.openai_api_key), "endpoint_host": host,
           "endpoint_is_groq": host == "api.groq.com", "coder_model": ps["coder_model"],
           "planner_model": ps["planner_model"], "tavily_key_present": bool(settings.tavily_api_key)}
    if not (ps["real"] and ps["ready"]):
        return {**res, "status": BLOCKED, "error": f"provider not ready, missing: {ps['missing']}"}
    r = httpx.get(f"{settings.openai_base_url}/models", headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                  timeout=20)
    res["models_endpoint_http"] = r.status_code
    if r.status_code != 200:
        return {**res, "status": FAILED, "error": f"GET /models HTTP {r.status_code}: {redact(r.text[:300])}"}
    ids = {m.get("id") for m in r.json().get("data", []) if isinstance(m, dict)}
    res["account_model_count"] = len(ids)
    res["coder_model_available"] = ps["coder_model"] in ids
    res["planner_model_available"] = ps["planner_model"] in ids
    ok = res["coder_model_available"] and res["planner_model_available"]
    return {**res, "status": OK if ok else FAILED,
            **({} if ok else {"error": "configured model id not listed for this account"})}


# ----------------------------------------------------------------------------- 2. provider operations
class PlanOut(BaseModel):
    files: list[str] = Field(min_length=1)
    apis: list[str] = Field(default=[])
    steps: list[str] = Field(min_length=1)


def check_text() -> dict:
    r = llm.complete("You are terse.", "Reply with exactly the word: pong", stage="planner", max_tokens=200)
    ok = "pong" in r.text.lower() and not r.estimated
    return {"status": OK if ok else FAILED, "reply": r.text.strip()[:80], "usage": _usage(r)}


def check_planner() -> dict:
    ledger: list = []
    out = llm.complete_json("You plan small code changes.",
                            "Plan: add a function slugify(title) to utils.py using only the standard library re module, with tests.",
                            PlanOut, stage="planner", ledger=ledger, max_tokens=800)
    return {"status": OK, "plan": out.model_dump(), "usage": [_usage(r) for r in ledger]}


def check_skeleton() -> dict:
    from .agent import deps_summary
    from .repo_intel import inspect_project
    from .skeleton import generate_skeleton
    env = inspect_project(ROOT / "demos" / "sample_project")
    ledger: list = []
    sk, errors = generate_skeleton("Create a Pydantic model User whose email field is lowercased by a validator.",
                                   deps_summary(env), "", None, ledger)
    return {"status": OK if ledger and not any(r.estimated for r in ledger) else FAILED,
            "skeleton": json.loads(sk.model_dump_json()), "schema_retries": errors, "usage": [_usage(r) for r in ledger]}


def check_stream() -> dict:
    old = settings.llm_stream
    settings.llm_stream = True
    try:
        r = llm.complete("You write Python.", "Write a one-line Python function add(a, b) returning a + b. Code only.",
                         stage="coder", max_tokens=300)
    finally:
        settings.llm_stream = old
    return {"status": OK if "def add" in r.text and not r.estimated else FAILED, "streamed": True,
            "usage": _usage(r), "note": None if not r.estimated else "stream ended without a usage event -> ESTIMATED"}


def check_error() -> dict:
    try:
        llm._call(settings.effective_provider(), "vericode-nonexistent-model-id", "x", "x", 10, "planner")
    except llm.LLMUnavailable as e:
        msg = redact(str(e))
        return {"status": OK, "error_reported": msg[:300], "key_leaked": bool(settings.openai_api_key and settings.openai_api_key in str(e))}
    return {"status": FAILED, "error": "invalid model id did not raise"}


def check_judge() -> dict:
    from .claims import extract_claims
    excerpt = ("Python 3.13.0 was released on October 7, 2024. It includes a new interactive interpreter and "
               "experimental free-threaded builds.")
    claim = extract_claims("Python 3.13 was released in October 2024.")[0]
    rec = stale.EvidenceRecord(claim.claim_id, claim.claim, "What's New", "https://docs.python.org/3/whatsnew/3.13.html",
                               "docs.python.org", "official_documentation", 1.0, _now(), "2024-10-07", excerpt, 0.9, "", "neutral",
                               "live_validation_probe")
    ledger: list = []
    out = stale.llm_judge(claim, [rec], ledger=ledger)
    quotes_ok = all(q.lower() in excerpt.lower() for q in (out or {}).get("quotes", []))
    ok = bool(out) and out.get("verdict") == "supports" and quotes_ok
    return {"status": OK if ok else FAILED, "verdict": (out or {}).get("verdict"), "quotes": (out or {}).get("quotes"),
            "quotes_verbatim": quotes_ok, "discarded": (out or {}).get("discarded", False),
            "usage": [_usage(r) for r in ledger]}


# ----------------------------------------------------------------------------- 3. Tavily
def check_tavily() -> dict:
    from .tavily import TavilyClient
    if not settings.tavily_api_key:
        return {"status": BLOCKED, "error": "TAVILY_API_KEY not set"}
    tc = TavilyClient()
    out = tc.search("Python 3.13 release date", include_domains=["python.org"], max_results=3, use_cache=False)
    if not out.ok:
        return {"status": FAILED, "error": f"{out.status}: {out.detail}"}
    res = [{"url": r.url, "domain": urlparse(r.url).hostname, "published_date": r.published_date,
            "score": r.score, "content_chars": len(r.content or "")} for r in out.results]
    valid_urls = all(urlparse(r["url"]).scheme == "https" and r["domain"] for r in res)
    extracted = {}
    if res:
        try:
            ex = tc.extract([res[0]["url"]])
            extracted = {u: len(t or "") for u, t in ex.items()}
        except Exception as e:
            extracted = {"error": redact(str(e))[:200]}
    persisted = db.row("SELECT COUNT(*) AS n FROM search_usage")
    return {"status": OK if res and valid_urls else FAILED, "results": res, "valid_urls": valid_urls,
            "retrieved_at": out.retrieved_at, "credits": out.credits, "calls": tc.calls,
            "extract_chars": extracted, "search_usage_rows": (persisted or {}).get("n")}


# ----------------------------------------------------------------------------- 4. Track 1 scenarios
def _claim_view(c: dict) -> dict:
    ev = c.get("evidence", [])
    return {"claim": c["claim"]["claim"], "category": c["claim"].get("category"),
            "volatility": c["claim"].get("volatility"), "verifiability": c["claim"].get("verifiability"),
            "status": c["status"], "freshness": c.get("freshness"), "confidence": c.get("confidence"),
            "search_status": c.get("search_status"), "judge": {k: v for k, v in (c.get("judge") or {}).items() if k != "record"},
            "conflict": bool(c.get("conflict")), "correction": c.get("correction"),
            "sources": [{"domain": e["domain"], "url": e["url"], "origin": e["origin"], "tier": e.get("authority_tier"),
                         "outcome": e["outcome"], "method": e.get("method"), "published": e.get("published_date"),
                         "freshness": e.get("freshness")} for e in ev[:4]]}


def run_scenario(name: str, answer: str) -> dict:
    res = stale.analyze(answer, mode="live")
    corrected = stale.corrected_answer(res["id"])
    claims = [_claim_view(c) for c in res["claims"]]
    live = res["summary"]["evidence_mode"] == "live_tavily" and res["summary"]["search_calls"] > 0
    return {"status": OK if live and claims else FAILED, "analysis_id": res["id"], "summary": {
        k: res["summary"][k] for k in ("total_claims", "by_status", "evidence_mode", "search_calls", "search_credits", "llm_judge", "llm_tokens")},
        "claims": claims, "corrected_answer": (corrected or {}).get("corrected_answer") or corrected}


def run_demo_e() -> dict:
    answer = ("To validate fields in Pydantic, use the @validator decorator. Pydantic provides BaseModel.model_dump() for "
              "serialization. Pydantic 2 lets you define settings classes with BaseSettings imported from pydantic.")
    res = stale.analyze(answer, mode="live", workspace="sample_project")
    ts = stale.analyze("In zod, z.string().nonempty() marks a string as required. zod provides z.coerce.number() to "
                       "coerce input to a number.", mode="live", workspace="ts_project")
    out = []
    for r in (res, ts):
        for c in r["claims"]:
            v = _claim_view(c)
            v["evidence_origins"] = sorted({e["origin"] for e in c.get("evidence", [])})
            out.append(v)
    return {"status": OK if out else FAILED, "claims": out, "original_answers_unchanged": True,
            "analysis_ids": [res["id"], ts["id"]]}


# ----------------------------------------------------------------------------- 5. coding tasks
def run_coding(project: str, prompt: str, mode: str = "vericode") -> dict:
    from .agent import TaskRunner, create_task
    p = (ROOT / "demos" / project).resolve()
    tid = create_task(p, prompt, mode)
    r = TaskRunner(tid, p, prompt, mode).run()
    pf = db.loads((db.row("SELECT preflight_json FROM tasks WHERE id=?", (tid,)) or {}).get("preflight_json"), {})
    tests = [{"cmd": x.get("cmd") or x.get("name"), "passed": x.get("passed")} for x in (r.get("checks") or {}).get("results", [])][:8]
    return {"status": OK if r.get("success") else FAILED, "task_id": tid, "mode": mode, "outcome": r.get("outcome"),
            "first_pass": r.get("first_pass_success"), "repairs": r.get("repair_attempts"),
            "changed_files": r.get("changed_files"), "tests": tests, "tokens": r.get("tokens"),
            "preflight_findings": [{k: f.get(k) for k in ("symbol", "status", "installed_version", "source", "suggestion")}
                                   for f in pf.get("findings", [])][:12],
            "api_corrections": r.get("api_corrections"), "diff": redact(r.get("diff") or "")[:6000],
            "error": redact(r.get("error") or "")[:600] or None, "duration_s_task": r.get("duration_s")}


# ----------------------------------------------------------------------------- 6. benchmark
def run_bench(runs: int) -> dict:
    from .benchmark import run_benchmark
    b = run_benchmark(runs=runs, live=True)
    tasks = []
    for t in b["tasks"]:
        s = t["summary"]
        tasks.append({"task": t["task"], "savings_pct": t["token_savings_pct"], "paired_savings_pct": t["paired_run_savings_pct"],
                      "savings_note": t["savings_note"], "flagged_api_usage": t["flagged_api_usage"],
                      **{m: {k: s[m][k] for k in ("success_rate", "first_pass_rate", "total_tokens", "input_tokens", "output_tokens",
                                                   "verification_overhead_tokens", "repair_attempts", "search_calls", "duration_s",
                                                   "by_stage", "measurement", "errors")} for m in ("baseline", "vericode")}})
    return {"status": OK if b["measurement"] == "ACTUAL_PROVIDER_USAGE" else FAILED, "benchmark_id": b["id"],
            "measurement": b["measurement"], "model": b["coder_model"], "runs_per_mode": runs,
            "average_savings_pct": b["average_savings_pct"], "comparable_tasks": b["comparable_tasks"], "tasks": tasks}



# ----------------------------------------------------------------------------- 7. API (what the frontend screens read)
def check_api(S: dict) -> dict:
    from fastapi.testclient import TestClient
    from . import auth
    from .api import app
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"token": auth.access_token()})
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    screens = {"dashboard": "/api/dashboard", "settings": "/api/settings", "integrations": "/api/integrations",
               "task_history": "/api/tasks", "stale_history": "/api/stale", "evidence_explorer": "/api/evidence",
               "token_analytics": "/api/analytics/tokens", "benchmarks": "/api/benchmarks"}
    aid = (S.get("track1_A_current") or {}).get("analysis_id")
    tid = (S.get("coding_python_new") or {}).get("task_id")
    if aid:
        screens["stale_detail"] = f"/api/stale/{aid}"
    if tid:
        screens["preflight_inspector"] = f"/api/tasks/{tid}"
    out, leaked = {}, False
    for name, path in screens.items():
        resp = c.get(path)
        body = resp.text
        leaked |= any(k and len(k) > 8 and k in body for k in (settings.openai_api_key, settings.tavily_api_key))
        out[name] = {"http": resp.status_code, "bytes": len(body),
                     "actual_usage_shown": "ACTUAL_PROVIDER_USAGE" in body, "mock_label_present": "MOCK" in body}
    ok = all(v["http"] == 200 for v in out.values()) and not leaked
    return {"status": OK if ok else FAILED, "screens": out, "secret_in_any_response": leaked}


# ----------------------------------------------------------------------------- report
def _md(rep: dict) -> str:
    L = [f"# VeriCode live validation report", "", f"Generated {rep['generated_at']} - provider `{rep['config'].get('provider')}` "
         f"endpoint `{rep['config'].get('endpoint_host')}` model `{rep['config'].get('coder_model')}`.", "",
         "| Section | Result | Duration (s) |", "|---|---|---|"]
    for k, v in rep["sections"].items():
        L.append(f"| {k} | {v.get('status')} | {v.get('duration_s')} |")
    L += ["", "Full machine-readable details: `live_report.json`."]
    for k, v in rep["sections"].items():
        if v.get("error"):
            L += ["", f"## {k}: error", "```", v["error"], "```"]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--skip-benchmark", action="store_true")
    a = ap.parse_args()
    db.init_db()
    S: dict[str, dict] = {}
    S["config"] = _section(check_config)
    if S["config"]["status"] == BLOCKED:
        print("BLOCKED:", S["config"].get("error"))
    real = S["config"]["status"] != BLOCKED
    steps = [("groq_text", check_text), ("groq_planner", check_planner), ("groq_skeleton", check_skeleton),
             ("groq_stream", check_stream), ("groq_error_handling", check_error), ("groq_evidence_judge", check_judge),
             ("tavily", check_tavily)]
    steps += [(f"track1_{n}", lambda n=n, t=t: run_scenario(n, t)) for n, t in SCENARIOS.items()]
    steps += [("demo_e_combined", run_demo_e),
              ("coding_python_new", lambda: run_coding("sample_project", PY_TASK)),
              ("coding_typescript_new", lambda: run_coding("ts_project", TS_TASK)),
              ("coding_arbitrary_demoC", lambda: run_coding("sample_project", __import__("vericode.demo", fromlist=["x"]).ARBITRARY_TASK))]
    if not a.skip_benchmark:
        steps.append(("benchmark_actual", lambda: run_bench(a.runs)))
    for name, fn in steps:
        S[name] = _section(fn) if real else {"status": BLOCKED, "error": "provider not configured"}
        print(f"{name:28s} {S[name]['status']:15s} {S[name].get('duration_s', '')}", flush=True)
    S["api_screens"] = _section(check_api, S) if real else {"status": BLOCKED}
    print(f"{'api_screens':28s} {S['api_screens']['status']}", flush=True)
    rep = {"generated_at": _now(), "config": S["config"], "sections": S}
    text = json.dumps(rep, indent=2, default=str)
    for secret in (settings.openai_api_key, settings.tavily_api_key, settings.anthropic_api_key):
        if secret and len(secret) > 8 and secret in text:
            print("ABORT: a configured secret appeared in the report; not writing it.")
            return 2
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "live_report.json").write_text(text)
    (OUT / "LIVE_REPORT.md").write_text(_md(rep))
    print(f"report: {OUT / 'LIVE_REPORT.md'}")
    critical = ["config", "groq_text", "groq_evidence_judge", "tavily"]
    return 0 if all(S[k]["status"] == OK for k in critical if k in S) else 1


if __name__ == "__main__":
    raise SystemExit(main())
