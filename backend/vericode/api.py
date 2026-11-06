"""FastAPI application - REST API contracts for every VeriCode module."""
from __future__ import annotations

import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, auth, benchmark, db, llm, memory, stale
from .config import ROOT, settings
from .repo_intel import inspect_project, select_relevant_files
from .security import SecurityError, network_isolation_available, resolve_workspace
from .skeleton import PlannedAPI, PlannedPackage, generate_skeleton
from .tavily import TavilyClient
from .verify_api import verify_planned_api, verify_skeleton

MAX_BODY = 256_000


@asynccontextmanager
async def lifespan(_app):
    print(f"\n  VeriCode login URL: {auth.login_url(int(os.environ.get('PORT', '8000')))}\n"
          f"  (token also stored in {auth.token_file()})\n", flush=True)
    yield


app = FastAPI(title="VeriCode API", version="2.0.0", description="Verify Before You Generate", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)
db.init_db()
settings.load_persisted()
if not auth.is_loopback_bind(settings.host) and not settings.allow_remote:
    raise RuntimeError(f"Refusing to serve on non-loopback host {settings.host!r} without VERICODE_ALLOW_REMOTE=1")


@app.middleware("http")
async def guard(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY:
        return JSONResponse({"detail": "request too large"}, status_code=413)
    if not auth.host_allowed(request.headers.get("host")):
        return JSONResponse({"detail": "host not allowed (set VERICODE_ALLOW_REMOTE=1 to expose)"}, status_code=403)
    ok, status, reason = auth.authorize(request.url.path, request.method, dict(request.cookies), dict(request.headers))
    if not ok:
        return JSONResponse({"detail": reason, "code": "auth"}, status_code=status)
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


class LoginReq(BaseModel):
    token: str = Field(min_length=1, max_length=200)


@app.post("/api/auth/login")
def login(req: LoginReq, response: Response):
    if not auth.check_token(req.token):
        raise HTTPException(401, "invalid access token")
    sid, csrf = auth.create_session()
    response.set_cookie(auth.SESSION_COOKIE, sid, httponly=True, samesite="strict", max_age=auth.SESSION_TTL, path="/")
    response.set_cookie(auth.CSRF_COOKIE, csrf, httponly=False, samesite="strict", max_age=auth.SESSION_TTL, path="/")
    return {"authenticated": True, "csrf": csrf}


@app.get("/api/auth/status")
def auth_status(request: Request):
    csrf = auth.session_csrf(request.cookies.get(auth.SESSION_COOKIE))
    return {"authenticated": csrf is not None, "csrf": csrf}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    auth.delete_session(request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    response.delete_cookie(auth.CSRF_COOKIE, path="/")
    return {"authenticated": False}


@app.exception_handler(SecurityError)
async def sec_handler(_, exc: SecurityError):
    return JSONResponse({"detail": f"security: {exc}"}, status_code=400)


@app.exception_handler(llm.LLMUnavailable)
async def llm_handler(_, exc: llm.LLMUnavailable):
    return JSONResponse({"detail": str(exc), "code": "llm_unavailable"}, status_code=503)


# ------------------------------------------------------------------ schemas
class PathReq(BaseModel):
    path: str = Field(min_length=1, max_length=500)


class SelectReq(PathReq):
    task: str = Field(min_length=3, max_length=4000)


class PreflightReq(SelectReq):
    live: bool = True


class VerifyApiReq(PathReq):
    package: str
    ecosystem: Literal["python", "node"] = "python"
    import_path: str
    name: str
    type: Literal["function", "class", "method", "decorator", "attribute", "module", "constant"] = "function"
    arguments: list[str] = []
    assumed_version: str | None = None
    live: bool = False


class TaskReq(BaseModel):
    path: str | None = None
    prompt: str | None = Field(default=None, max_length=8000)
    mode: Literal["vericode", "baseline"] = "vericode"
    max_repairs: int | None = Field(default=None, ge=0, le=5)
    live: bool = True
    catalog_id: str | None = None


class StaleReq(BaseModel):
    answer: str = Field(min_length=10, max_length=20000)
    question: str | None = Field(default=None, max_length=2000)
    urls: list[str] = Field(default=[], max_length=5)
    preferred_domains: list[str] = Field(default=[], max_length=10)
    mode: Literal["live", "fixture"] = "live"


class BenchReq(BaseModel):
    task_ids: list[str] = []
    runs: int = Field(default=1, ge=1, le=5)
    max_repairs: int | None = Field(default=None, ge=0, le=5)
    live: bool = True


class RuleUpdate(BaseModel):
    correction: str | None = None
    issue: str | None = None
    active: int | None = None
    version_spec: str | None = None


# ------------------------------------------------------------------ system
@app.get("/api/health")
def health():
    return {"ok": True, "provider": settings.effective_provider(), "tavily_configured": bool(settings.tavily_api_key),
            "network_isolation": network_isolation_available(), "time": time.time()}


@app.get("/api/settings")
def get_settings():
    return settings.public_dict()


@app.put("/api/settings")
def put_settings(data: dict):
    if any(k.endswith("api_key") for k in data):
        raise HTTPException(400, "API keys are configured via environment variables only (.env), never via the browser.")
    try:
        settings.update(data)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return settings.public_dict()


@app.get("/api/workspaces")
def workspaces():
    root = Path(settings.workspaces_root)
    out = []
    for p in sorted(root.iterdir()) if root.is_dir() else []:
        if p.is_dir() and not p.name.startswith((".", "_")) and p.name not in ("tasks", "stale_fixtures"):
            out.append({"name": p.name, "path": str(p.resolve())})
    return out


# ------------------------------------------------------------------ project intelligence + preflight
@app.post("/api/projects/inspect")
def inspect(req: PathReq):
    env = inspect_project(resolve_workspace(req.path))
    return env.to_dict()


@app.post("/api/projects/select-files")
def select_files(req: SelectReq):
    env = inspect_project(resolve_workspace(req.path))
    return {"files": select_relevant_files(env, req.task)}


@app.post("/api/preflight")
def preflight(req: PreflightReq):
    root = resolve_workspace(req.path)
    env = inspect_project(root)
    tid = agent.create_task(root, req.task, "preflight")
    ledger: list = []
    sel = select_relevant_files(env, req.task)
    sk, errs = generate_skeleton(req.task, agent.deps_summary(env), agent.outline(env, [s["path"] for s in sel]), tid, ledger)
    client = TavilyClient()
    findings = [f.to_dict() for f in verify_skeleton(env, sk, client, live=req.live)]
    rules = [r for r in (memory.save_from_finding(f) for f in findings) if r]
    res = {"selected_files": sel, "skeleton": sk.model_dump(), "skeleton_errors": errs, "findings": findings,
           "briefing": agent.build_briefing(findings), "tokens": agent.summarize_ledger(ledger),
           "tavily_calls": client.calls, "tavily_configured": bool(client.api_key), "rules_saved": [r["id"] for r in rules]}
    with db.tx() as c:
        c.execute("UPDATE tasks SET status='succeeded', finished_at=?, success=1, preflight_json=?, result_json=? WHERE id=?",
                  (time.time(), db.dumps(res), db.dumps({"tokens": res["tokens"], "mode": "preflight"}), tid))
    res["task_id"] = tid
    return res


@app.post("/api/verify-api")
def verify_api(req: VerifyApiReq):
    env = inspect_project(resolve_workspace(req.path))
    pkg = PlannedPackage(package=req.package, ecosystem=req.ecosystem, assumed_version=req.assumed_version,
                         planned_apis=[PlannedAPI(import_path=req.import_path, name=req.name, type=req.type, arguments=req.arguments)])
    f = verify_planned_api(env, pkg, pkg.planned_apis[0])
    if req.live:
        from .verify_api import live_verify
        live_verify(f, env, TavilyClient())
    return f.to_dict()


# ------------------------------------------------------------------ coding tasks
@app.get("/api/catalog")
def catalog():
    return agent.load_catalog()


@app.post("/api/tasks")
def create_task(req: TaskReq):
    acceptance = None
    path, prompt = req.path, req.prompt
    if req.catalog_id:
        t = next((x for x in agent.load_catalog() if x["id"] == req.catalog_id), None)
        if not t:
            raise HTTPException(404, "unknown catalog task")
        path, prompt, acceptance = path or t["project"], prompt or t["prompt"], t.get("acceptance_tests")
    if not path or not prompt:
        raise HTTPException(400, "path and prompt are required (or a catalog_id)")
    root = resolve_workspace(path)
    if settings.effective_provider() == "none":
        raise llm.LLMUnavailable("No LLM provider configured")
    tid = agent.run_task_async(root, prompt, req.mode, req.max_repairs, req.live, acceptance)
    return {"task_id": tid}


def _task_out(t: dict, full: bool = True) -> dict:
    out = {k: t[k] for k in ("id", "project_path", "prompt", "mode", "status", "created_at", "finished_at", "success", "provider", "benchmark_id")}
    res = db.loads(t["result_json"], {})
    out["tokens"] = res.get("tokens")
    out["changed_files"] = res.get("changed_files", [])
    out["error"] = res.get("error")
    if full:
        out["result"] = res
        out["preflight"] = db.loads(t["preflight_json"], {})
        out["events"] = db.loads(t["events_json"], [])
    return out


@app.get("/api/tasks")
def list_tasks(limit: int = 100):
    return [_task_out(t, full=False) for t in db.rows("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (min(limit, 500),))]


@app.get("/api/tasks/{tid}")
def get_task(tid: str):
    t = db.row("SELECT * FROM tasks WHERE id=?", (tid,))
    if not t:
        raise HTTPException(404, "task not found")
    return _task_out(t)


@app.post("/api/tasks/{tid}/apply")
def apply_task(tid: str):
    try:
        return agent.apply_changes(tid)
    except KeyError:
        raise HTTPException(404, "task not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


# ------------------------------------------------------------------ stale-answer detection
@app.post("/api/stale/analyze")
def stale_analyze(req: StaleReq):
    return stale.analyze(req.answer, req.question, req.urls, req.preferred_domains, req.mode)


@app.get("/api/stale/demo")
def stale_demo():
    import json
    return json.loads((ROOT / "demos" / "stale_fixtures" / "demo2.json").read_text())


@app.get("/api/stale")
def stale_list():
    return [{"id": a["id"], "answer": a["answer"][:200], "evidence_mode": a["evidence_mode"], "created_at": a["created_at"],
             "summary": db.loads(a["summary_json"])} for a in db.rows("SELECT * FROM analyses ORDER BY created_at DESC LIMIT 100")]


@app.get("/api/stale/{aid}")
def stale_get(aid: str):
    a = stale.load_analysis(aid)
    if not a:
        raise HTTPException(404, "analysis not found")
    return a


@app.post("/api/stale/{aid}/correct")
def stale_correct(aid: str):
    try:
        return stale.corrected_answer(aid)
    except KeyError:
        raise HTTPException(404, "analysis not found")


@app.get("/api/evidence")
def evidence(analysis_id: str | None = None, limit: int = 200):
    if analysis_id:
        rows = db.rows("SELECT e.*, c.claim, c.status FROM evidence e LEFT JOIN claims c ON c.analysis_id=e.analysis_id AND c.claim_id=e.claim_id WHERE e.analysis_id=?", (analysis_id,))
    else:
        rows = db.rows("SELECT e.*, c.claim, c.status FROM evidence e LEFT JOIN claims c ON c.analysis_id=e.analysis_id AND c.claim_id=e.claim_id ORDER BY e.retrieved_at DESC LIMIT ?", (min(limit, 1000),))
    return rows


# ------------------------------------------------------------------ analytics, benchmarks, dashboard
@app.get("/api/analytics/tokens")
def token_analytics():
    by_stage = db.rows("SELECT stage, SUM(input_tokens) input, SUM(output_tokens) output, COUNT(*) calls, SUM(estimated) estimated_calls FROM token_usage GROUP BY stage")
    by_mode = db.rows("SELECT t.mode, SUM(u.input_tokens) input, SUM(u.output_tokens) output, COUNT(*) calls, SUM(u.estimated) estimated_calls "
                      "FROM token_usage u JOIN tasks t ON t.id=u.task_id GROUP BY t.mode")
    per_task = db.rows("SELECT t.id, t.mode, t.prompt, t.success, t.created_at, SUM(u.input_tokens) input, SUM(u.output_tokens) output, "
                       "COUNT(u.id) calls, MAX(u.estimated) estimated FROM tasks t LEFT JOIN token_usage u ON u.task_id=t.id "
                       "GROUP BY t.id ORDER BY t.created_at DESC LIMIT 50")
    for t in per_task:
        res = db.loads((db.row("SELECT result_json FROM tasks WHERE id=?", (t["id"],)) or {}).get("result_json"), {})
        t["repair_attempts"] = res.get("repair_attempts")
        t["search_calls"] = res.get("search_calls")
    cache_hits = db.row("SELECT COUNT(*) n FROM cache")["n"]
    return {"by_stage": by_stage, "by_mode": by_mode, "per_task": per_task, "cache_entries": cache_hits,
            "cost_per_mtok": {"input": settings.cost_input_per_mtok, "output": settings.cost_output_per_mtok}}


_bench_state: dict = {"running": False, "error": None}


@app.post("/api/benchmarks")
def start_benchmark(req: BenchReq):
    if _bench_state["running"]:
        raise HTTPException(409, "a benchmark is already running")
    if settings.effective_provider() == "none":
        raise llm.LLMUnavailable("No LLM provider configured")

    def go():
        _bench_state.update(running=True, error=None)
        try:
            benchmark.run_benchmark(req.task_ids or None, req.runs, req.max_repairs, req.live)
        except Exception as e:  # surfaced via GET
            _bench_state["error"] = str(e)
        finally:
            _bench_state["running"] = False
    threading.Thread(target=go, daemon=True).start()
    return {"started": True}


@app.get("/api/benchmarks")
def list_benchmarks():
    return {"running": _bench_state["running"], "error": _bench_state["error"],
            "results": [db.loads(b["result_json"]) for b in db.rows("SELECT * FROM benchmarks ORDER BY created_at DESC LIMIT 20")]}


@app.get("/api/dashboard")
def dashboard():
    q = lambda sql, p=(): db.row(sql, p)  # noqa: E731
    tok = q("SELECT COALESCE(SUM(input_tokens+output_tokens),0) n, COALESCE(SUM(estimated),0) est, COUNT(*) calls FROM token_usage")
    latest_bench = db.row("SELECT result_json FROM benchmarks ORDER BY created_at DESC LIMIT 1")
    return {
        "coding_tasks": q("SELECT COUNT(*) n FROM tasks WHERE mode IN ('vericode','baseline')")["n"],
        "successful_tasks": q("SELECT COUNT(*) n FROM tasks WHERE success=1 AND mode IN ('vericode','baseline')")["n"],
        "preflight_runs": q("SELECT COUNT(*) n FROM tasks WHERE mode IN ('vericode','preflight') AND preflight_json IS NOT NULL")["n"],
        "stale_claims": q("SELECT COUNT(*) n FROM claims WHERE status IN ('CONTRADICTED','POTENTIALLY_STALE')")["n"],
        "claims_checked": q("SELECT COUNT(*) n FROM claims")["n"],
        "total_tokens": tok["n"], "llm_calls": tok["calls"], "estimated_calls": tok["est"],
        "latest_benchmark": db.loads(latest_bench["result_json"]) if latest_bench else None,
        "recent_tasks": [_task_out(t, full=False) for t in db.rows("SELECT * FROM tasks ORDER BY created_at DESC LIMIT 8")],
        "provider": settings.effective_provider(), "tavily_configured": bool(settings.tavily_api_key),
        "rules": q("SELECT COUNT(*) n FROM rules WHERE active=1")["n"],
    }


# ------------------------------------------------------------------ project memory
@app.get("/api/rules")
def rules():
    return memory.list_rules()


@app.put("/api/rules/{rid}")
def rule_update(rid: str, req: RuleUpdate):
    r = memory.update_rule(rid, req.model_dump(exclude_none=True))
    if not r:
        raise HTTPException(404, "rule not found")
    return r


@app.delete("/api/rules/{rid}")
def rule_delete(rid: str):
    memory.delete_rule(rid)
    return {"deleted": rid}


@app.post("/api/rules/export")
def rule_export(req: PathReq):
    p = memory.export_rules(resolve_workspace(req.path))
    return {"written": str(p), "content": p.read_text()}


# ------------------------------------------------------------------ frontend (built assets)
DIST = ROOT / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(DIST / "index.html")
