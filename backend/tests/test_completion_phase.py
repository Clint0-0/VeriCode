"""Tests for the completion phase: claims, semantic verification, authority, LLM providers + judge,
TypeScript compiler checks, docker sandbox, auth/CSRF, settings + schema persistence, conflicts."""
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from vericode import agent, auth, db, jsinspect, llm, security, stale
from vericode.claims import extract_claims, split_compound
from vericode.config import ROOT, settings

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)
TS_PROJECT = ROOT / "demos" / "ts_project"
needs_ts = pytest.mark.skipif(not (jsinspect.ts_checker_available() and (TS_PROJECT / "node_modules").is_dir()),
                              reason="TypeScript checker or demos/ts_project/node_modules missing (scripts/setup.sh)")
needs_docker = pytest.mark.skipif(not security.docker_available(), reason="Docker daemon not reachable")


# ---------------------------------------------------------------- claim extraction
def test_compound_split_with_subject_carry_over():
    assert split_compound("FastAPI supports async endpoints and requires Python 3.8 or newer.") == [
        "FastAPI supports async endpoints.", "FastAPI requires Python 3.8 or newer."]
    assert split_compound("Rust is fast, and Go is simple.") == ["Rust is fast.", "Go is simple."]


def test_spans_traceable_across_paragraphs_and_bullets():
    a = "Intro line here.\n\n- ChatGPT Plus costs $20 per month; Satya Nadella is the CEO of Microsoft.\n1. Django 4.2 is an LTS release."
    cs = extract_claims(a)
    for c in cs:
        assert c.source_text == a[c.span[0]:c.span[1]]
    assert [c.category for c in cs if c.requires_verification] == ["pricing", "leadership", "software_version"]


def test_negation_conditional_opinion_ranges():
    cs = {c.claim: c for c in extract_claims(
        "Python 2 is no longer supported. If you use Node 18, it reaches end of life in 2025. "
        "I think Rust is the best language. The GDPR applied from 2018 to 2024 in its first form.")}
    neg = next(c for k, c in cs.items() if k.startswith("Python 2"))
    assert neg.negated and neg.requires_verification
    cond = next(c for k, c in cs.items() if k.startswith("If you use"))
    assert cond.conditional and cond.verifiability == "conditional"
    op = next(c for k, c in cs.items() if k.startswith("I think"))
    assert op.verifiability == "opinion" and not op.requires_verification
    rng = next(c for k, c in cs.items() if k.startswith("The GDPR"))
    assert rng.values["date_range"] == ["2018-2024"] and rng.evidence_type == "government_or_regulator_source"


def test_stable_facts_skip_live_search(tmp_path):
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"sources": []}))
    s = stale.FixtureSearch(p)
    stale.analyze("Water is a chemical compound. Python was created by Guido van Rossum.", search=s, now=NOW)
    assert s.calls == 0


# ---------------------------------------------------------------- semantic verification
def fx(tmp_path, sources):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"sources": sources}))
    return p


FASTAPI = {"title": "FastAPI async", "url": "https://fastapi.tiangolo.com/async/", "published_date": None,
           "keywords": ["fastapi", "asynchronous", "endpoint", "functions", "synchronous", "support", "supports"], "min_match": 2,
           "content": "FastAPI supports asynchronous endpoint functions declared with async def, and it also supports normal synchronous def functions."}


def test_semantic_support_without_concrete_values(tmp_path):
    r = stale.analyze("FastAPI supports asynchronous endpoint functions.", mode="fixture", fixture=fx(tmp_path, [FASTAPI]), now=NOW)
    c = r["claims"][0]
    assert c["status"] == "CURRENT_SUPPORTED" and c["confidence_breakdown"]["method_penalty"] == -10


def test_semantic_negation_contradiction(tmp_path):
    r = stale.analyze("FastAPI does not support synchronous endpoint functions.", mode="fixture", fixture=fx(tmp_path, [FASTAPI]), now=NOW)
    assert r["claims"][0]["status"] == "CONTRADICTED"


def test_value_match_requires_matching_statement(tmp_path):
    src = {"title": "3.14", "url": "https://docs.python.org/3.14/whatsnew/3.14.html", "published_date": "2025-10-07",
           "keywords": ["python", "3.14", "removed", "distutils"], "min_match": 2,
           "content": "Python 3.14 adds template strings and an experimental JIT."}
    r = stale.analyze("Python 3.14 removed the distutils module.", mode="fixture", fixture=fx(tmp_path, [src]), now=NOW)
    assert r["claims"][0]["status"] == "UNVERIFIED"  # version mentioned, statement not established


def test_conflict_details_both_sides(tmp_path):
    r = stale.analyze("The Acme Cloud Pro plan costs $30 per month.", mode="fixture",
                      fixture=ROOT / "demos" / "stale_fixtures" / "conflict_synthetic.json", now=NOW)
    c = r["claims"][0]
    assert c["status"] == "CONFLICTING_EVIDENCE"
    assert c["conflict"]["supporting"][0]["url"] != c["conflict"]["contradicting"][0]["url"]
    assert "no publication date" in c["conflict"]["reason"] and {e["origin"] for e in c["evidence"]} == {"fixture_synthetic"}


def test_corrected_answer_preserves_original_and_explains_missing(tmp_path):
    srcs = [{"title": "Pricing", "url": "https://openai.com/chatgpt/pricing", "published_date": "2026-10-01",
             "keywords": ["chatgpt", "plus", "pricing"], "content": "ChatGPT Plus subscription is $25 per month."}]
    a = "ChatGPT Plus costs $20 per month.\nThe Foo Foundation plans to merge with Bar by 2030."
    r = stale.analyze(a, mode="fixture", fixture=fx(tmp_path, srcs), now=NOW)
    out = stale.corrected_answer(r["id"])
    assert out["original"] == a
    assert out["corrected"].startswith("ChatGPT Plus costs $25 per month. [1]")
    assert "[unverified:" in out["corrected"] and "\n" in out["corrected"]  # paragraph structure kept
    assert out["citations"][0]["url"] == "https://openai.com/chatgpt/pricing"


# ---------------------------------------------------------------- authority
def test_authority_configurable_and_entity_aware(monkeypatch):
    assert stale.authority("https://news.microsoft.com/x", category="leadership", claim_terms=["satya", "microsoft"])[1] == "official_entity_site"
    assert stale.authority("https://www.sec.gov/x")[1] == "government"
    monkeypatch.setitem(settings.authority_rules, "pricing", ["acme.test"])
    assert stale.authority("https://shop.acme.test/p", category="pricing")[1] == "primary_source_for_pricing"
    assert stale.authority("https://medium.com/@a/b", category="pricing", claim_terms=["medium"])[0] == 0.35


# ---------------------------------------------------------------- LLM providers (mocked HTTP transport)
def test_anthropic_request_and_actual_usage(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    monkeypatch.setattr(settings, "coder_model", "model-under-test")
    monkeypatch.setattr(settings, "llm_stream", False)
    seen = {}

    def h(req):
        seen["headers"], seen["body"] = dict(req.headers), json.loads(req.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "hi"}],
                                         "usage": {"input_tokens": 11, "output_tokens": 3, "cache_read_input_tokens": 4}})
    r = llm.complete("sys", "hello", "coder", transport=httpx.MockTransport(h))
    assert (r.input_tokens, r.output_tokens, r.measurement) == (15, 3, "ACTUAL_PROVIDER_USAGE")
    assert seen["headers"]["anthropic-version"] == "2023-06-01" and seen["body"]["model"] == "model-under-test"
    assert seen["body"]["system"] == "sys" and seen["body"]["messages"][0]["role"] == "user"


def test_openai_request_uses_max_completion_tokens(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-00000000000000000000")
    monkeypatch.setattr(settings, "coder_model", "m")
    seen = {}

    def h(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 7, "completion_tokens": 2}})
    r = llm.complete("s", "p", "planner", transport=httpx.MockTransport(h))
    assert "max_completion_tokens" in seen["body"] and r.measurement == "ACTUAL_PROVIDER_USAGE"


def test_real_provider_failure_is_an_error_not_mock(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    monkeypatch.setattr(settings, "coder_model", "m")
    with pytest.raises(llm.LLMUnavailable, match="HTTP 401"):
        llm.complete("s", "p", "coder", transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "bad key"})))
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(llm.LLMUnavailable, match="ANTHROPIC_API_KEY"):
        llm.complete("s", "p", "coder")


def test_provider_status_lists_missing_env(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "coder_model", "")
    monkeypatch.setattr(settings, "planner_model", "")
    st = llm.provider_status()
    assert not st["ready"] and "OPENAI_API_KEY" in st["missing"] and "VERICODE_CODER_MODEL" in st["missing"]


def test_structured_output_validation_and_retry(monkeypatch):
    from pydantic import BaseModel

    class Out(BaseModel):
        verdict: str
    replies = iter(["no json", '{"verdict": "supports"}'])
    monkeypatch.setattr(llm, "complete", lambda *a, **k: llm.LLMResult(next(replies), 1, 1, False, "anthropic", "m", "claim_judge"))
    assert llm.complete_json("s", "p", Out, "claim_judge").verdict == "supports"


def test_llm_judge_rejects_unquoted_verdicts(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    monkeypatch.setattr(settings, "coder_model", "m")
    src = {"title": "doc", "url": "https://docs.example.dev/streaming", "published_date": None,
           "keywords": ["widgetlib", "streaming", "responses"], "min_match": 2,
           "content": "WidgetLib can deliver responses incrementally over server-sent events."}
    verdicts = iter([
        '{"verdict":"supports","supporting_quotes":["WidgetLib supports streaming"],"sufficient":true}',  # quote not in source
        '{"verdict":"supports","supporting_quotes":["deliver responses incrementally over server-sent events"],"sufficient":true}',
    ])
    monkeypatch.setattr(llm, "_call", lambda *a, **k: llm.LLMResult(next(verdicts), 50, 10, False, "anthropic", "m", "claim_judge"))
    r1 = stale.analyze("WidgetLib supports streaming responses.", mode="fixture", fixture=fx(tmp_path, [src]), now=NOW)
    assert r1["claims"][0]["status"] == "UNVERIFIED" and r1["claims"][0]["judge"]["discarded"]
    r2 = stale.analyze("WidgetLib supports streaming responses.", mode="fixture", fixture=fx(tmp_path, [src]), now=NOW)
    c = r2["claims"][0]
    assert c["status"] == "CURRENT_SUPPORTED" and c["evidence"][0]["method"] == "llm_judge"
    assert r2["summary"]["llm_tokens"]["measurement"] == "ACTUAL_PROVIDER_USAGE"


def test_tavily_spec_fields_and_quota(monkeypatch):
    from vericode.tavily import TavilyClient
    seen = {}

    def h(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"query": "q", "results": [], "usage": {"credits": 1}})
    c = TavilyClient(api_key="tvly-x", transport=httpx.MockTransport(h))
    out = c.search("python release", include_domains=["python.org"], use_cache=False)
    b = seen["body"]
    assert b["include_published_date"] is True and b["include_usage"] is True and b["include_domains_mode"] == "prefer"
    assert out.credits == 1 and db.row("SELECT COUNT(*) n FROM search_usage")["n"] == 1
    q = TavilyClient(api_key="tvly-x", transport=httpx.MockTransport(lambda r: httpx.Response(432)))
    assert q.search("x", use_cache=False).status == "quota_exceeded"


# ---------------------------------------------------------------- TypeScript compiler API
@needs_ts
def test_ts_compiler_detects_deprecated_mistyped_and_missing():
    from vericode.repo_intel import inspect_project
    from vericode.skeleton import PlannedAPI, PlannedPackage
    from vericode.verify_api import verify_planned_api
    env = inspect_project(TS_PROJECT, use_cache=False)
    assert env.dep("zod").installed == "3.23.8" and len(env.dependencies) < 10  # transitive lock entries excluded
    pkg = PlannedPackage(package="zod", ecosystem="node", planned_apis=[
        PlannedAPI(import_path="zod", name="ZodString.nonempty", type="method", arguments=[]),
        PlannedAPI(import_path="zod", name="ZodString.min", type="method", arguments=['"3"']),
        PlannedAPI(import_path="zod", name="ZodString.max", type="method", arguments=["5", '"m"', "true"]),
        PlannedAPI(import_path="zod", name="ZodString.min", type="method", arguments=["3"]),
        PlannedAPI(import_path="zod", name="ZodString.nope", type="method", arguments=[]),
        PlannedAPI(import_path="zod", name="nothere", type="function"),
        PlannedAPI(import_path="zod-missing", name="x", type="function"),
    ])
    st = [verify_planned_api(env, pkg, a) for a in pkg.planned_apis]
    assert st[0].status == "DEPRECATED" and "min(1)" in st[0].suggested_correction
    assert st[1].status == "INCOMPATIBLE" and "TS2345" in st[1].explanation
    assert st[2].status == "INCOMPATIBLE" and "TS2554" in st[2].explanation
    assert st[3].status == "VERIFIED_LOCAL" and st[3].verification_confidence == "high"
    assert [s.status for s in st[4:]] == ["NOT_FOUND", "NOT_FOUND", "NOT_FOUND"]
    assert st[0].local["signatures"][0]["min_args"] == 0 and st[1].local["signatures"][0]["params"][0]["type"] == "number"


@needs_ts
def test_ts_default_and_generic_signatures(tmp_path):
    nm = tmp_path / "node_modules" / "gen"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text(json.dumps({"name": "gen", "version": "2.0.0", "types": "index.d.ts"}))
    (nm / "index.d.ts").write_text("export default function make<T extends string>(x: T, n?: number): T;\nexport declare function pick<K extends keyof {a:1}>(k: K): K;\n")
    r = jsinspect.ts_compiler_check(tmp_path, "gen", "default", "", ["5"])
    assert r["export_kind"] == "default" and r["signatures"][0]["type_params"][0]["constraint"] == "string"
    assert r["call_check"]["ok"] is False
    assert jsinspect.ts_compiler_check(tmp_path, "gen", "pick", "", ['"a"'])["call_check"]["ok"] is True


# ---------------------------------------------------------------- coding agent
def test_partial_when_no_tests(tmp_path, monkeypatch):
    proj = tmp_path / "ws" / "p"
    (proj / "pkg").mkdir(parents=True)
    (proj / "pkg" / "a.py").write_text("X = 1\n")
    monkeypatch.setattr(agent, "RUNS_DIR", tmp_path / "runs")
    reply = "FILE: pkg/a.py\n<<<<<<< SEARCH\nX = 1\n=======\nX = 2\n>>>>>>> REPLACE\n"
    def fake(system, prompt, stage, task_id=None, max_tokens=0, ledger=None, transport=None):
        r = llm.LLMResult(reply if stage != "planner" else '{"packages": []}', 5, 5, True, "mock", "m", stage)
        ledger.append(r)
        return r
    monkeypatch.setattr(llm, "complete", fake)
    tid = agent.create_task(proj, "change X to 2", "vericode")
    r = agent.TaskRunner(tid, proj, "change X to 2", "vericode", 1).run()
    assert r["outcome"] == "partial", r.get("error") and not r["success"] and "UNVALIDATED" in r["checks"]["note"]


def test_conflict_report_contains_user_diff(sample_project, tmp_path, monkeypatch):
    proj = tmp_path / "ws" / "proj"
    shutil.copytree(sample_project, proj, symlinks=True, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
    (proj / ".venv").symlink_to(sample_project / ".venv")
    monkeypatch.setattr(agent, "RUNS_DIR", tmp_path / "runs")
    t = next(x for x in agent.load_catalog() if x["id"] == "summary")
    tid = agent.create_task(proj, t["prompt"], "vericode")
    agent.TaskRunner(tid, proj, t["prompt"], "vericode", 1, acceptance=t["acceptance_tests"]).run()
    f = proj / "taskboard" / "storage.py"
    f.write_text(f.read_text() + "\n# local edit by user\n")
    with pytest.raises(agent.ApplyConflict) as ei:
        agent.apply_changes(tid)
    assert ei.value.conflicts[0]["state"] == "modified" and "+# local edit by user" in ei.value.conflicts[0]["user_diff"]


def test_conventions_injected(sample_project):
    from vericode.repo_intel import conventions_text, inspect_project
    txt = conventions_text(inspect_project(sample_project))
    assert "4 spaces" in txt and "pytest" in txt


def test_ts_task_vericode_vs_baseline(monkeypatch):
    if not (TS_PROJECT / "node_modules").is_dir() or not jsinspect.ts_checker_available():
        pytest.skip("ts demo not installed")
    t = next(x for x in agent.load_catalog() if x["id"] == "signup")
    v = agent.TaskRunner(agent.create_task(TS_PROJECT, t["prompt"], "vericode"), TS_PROJECT, t["prompt"], "vericode", 3,
                         acceptance=t["acceptance_tests"]).run()
    b = agent.TaskRunner(agent.create_task(TS_PROJECT, t["prompt"], "baseline"), TS_PROJECT, t["prompt"], "baseline", 3,
                         acceptance=t["acceptance_tests"]).run()
    assert v["outcome"] == "succeeded" and v["first_pass_success"] and ".min(3)" in v["diff"] and "nonempty" not in v["diff"]
    assert b["outcome"] == "succeeded" and not b["first_pass_success"] and "nonempty()" in b["diff"]  # deprecated API slipped through


# ---------------------------------------------------------------- sandbox
def test_process_sandbox_labels_network(tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    r = security.run_command(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], tmp_path, backend="process")
    assert r.returncode == 0 and r.isolation.startswith("process:")
    assert ("no-network" in r.isolation) == security.network_isolation_available()


@needs_docker
def test_docker_sandbox_enforces_isolation(tmp_path, sample_project):
    (tmp_path / "test_iso.py").write_text(
        "import os, socket, pytest\n"
        "def test_no_network():\n"
        "    with pytest.raises(OSError):\n        socket.create_connection(('1.1.1.1', 53), timeout=2)\n"
        "def test_not_root_and_readonly():\n"
        "    assert os.getuid() == 65534\n"
        "    with pytest.raises(OSError):\n        open('/etc/vc_probe', 'w')\n"
        "    with pytest.raises(OSError):\n        open('/usr/vc_probe', 'w')\n"
        "def test_secrets_absent():\n"
        "    assert not any(k.endswith('API_KEY') for k in os.environ)\n"
        "    assert not os.path.exists('/root') or not os.access('/root', os.R_OK)\n")
    os.environ["TAVILY_API_KEY"] = "tvly-should-not-leak-000"
    try:
        r = security.run_command(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], tmp_path, backend="docker",
                                 ro_mounts={".venv": sample_project / ".venv"})
    finally:
        del os.environ["TAVILY_API_KEY"]
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.isolation.startswith("docker: --network none")


@needs_docker
def test_docker_timeout_kills_container(tmp_path, sample_project):
    (tmp_path / "test_slow.py").write_text("import time\ndef test_slow():\n    time.sleep(30)\n")
    t0 = time.time()
    r = security.run_command(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], tmp_path, timeout=5, backend="docker",
                             ro_mounts={".venv": sample_project / ".venv"})
    assert r.timed_out and time.time() - t0 < 25


def test_explicit_docker_request_never_downgrades(monkeypatch):
    monkeypatch.setattr(settings, "sandbox_backend", "docker")
    monkeypatch.setattr(security, "_DOCKER_OK", False)
    with pytest.raises(security.SecurityError, match="not reachable"):
        security.sandbox_backend()


# ---------------------------------------------------------------- auth / CSRF / host
def test_auth_required_and_csrf_enforced():
    from vericode.api import app
    anon = TestClient(app)
    assert anon.get("/api/health").status_code == 200
    assert anon.get("/api/tasks").status_code == 401
    assert anon.post("/api/auth/login", json={"token": "wrong"}).status_code == 401
    r = anon.post("/api/auth/login", json={"token": auth.access_token()})
    assert r.status_code == 200 and "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert anon.get("/api/tasks").status_code == 200  # cookie session
    assert anon.put("/api/settings", json={"max_repair_attempts": 2}).status_code == 403  # no CSRF header
    assert anon.put("/api/settings", json={"max_repair_attempts": 2}, headers={"X-CSRF-Token": r.json()["csrf"]}).status_code == 200
    bearer = TestClient(app)
    assert bearer.get("/api/tasks", headers={"Authorization": f"Bearer {auth.access_token()}"}).status_code == 200
    anon.post("/api/auth/logout", headers={"X-CSRF-Token": r.json()["csrf"]})
    assert anon.get("/api/tasks").status_code == 401


def test_dns_rebinding_host_header_blocked():
    from vericode.api import app
    c = TestClient(app)
    assert c.get("/api/health", headers={"Host": "evil.example.com"}).status_code == 403


def test_refuses_remote_bind_without_opt_in():
    assert auth.is_loopback_bind("127.0.0.1") and not auth.is_loopback_bind("0.0.0.0")


def test_settings_never_expose_secrets(client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-supersecret-123456")
    body = client.get("/api/settings").text
    assert "supersecret" not in body and '"tavily_configured":true' in body.replace(" ", "")
    assert client.put("/api/settings", json={"openai_api_key": "x"}).status_code == 400


# ---------------------------------------------------------------- persistence
def test_settings_persist_across_restart(client):
    client.put("/api/settings", json={"max_repair_attempts": 1, "half_lives": {"pricing": 30}, "use_llm_judge": "false",
                                      "authority_rules": {"pricing": ["acme.test"]}})
    settings.max_repair_attempts, settings.half_lives["pricing"], settings.use_llm_judge = 3, 60, True
    settings.authority_rules = {}
    db._conn = None  # simulate process restart
    db.init_db()
    settings.load_persisted()
    assert settings.max_repair_attempts == 1 and settings.half_lives["pricing"] == 30 and settings.use_llm_judge is False
    assert settings.authority_rules["pricing"] == ["acme.test"]


def test_schema_migrations_idempotent_and_history_survives(tmp_path):
    db.init_db()
    v = db.schema_version()
    with db.tx() as c:
        c.execute("INSERT INTO tasks(id,prompt,mode,status,created_at) VALUES('t_keep','p','vericode','succeeded',1)")
    db._conn = None
    db.init_db()
    assert db.schema_version() == v >= 7
    assert db.row("SELECT id FROM tasks WHERE id='t_keep'")


# ---------------------------------------------------------------- live integration (opt-in, real network)
live = pytest.mark.live
skip_live = pytest.mark.skipif(os.environ.get("VERICODE_LIVE_TESTS") != "1", reason="set VERICODE_LIVE_TESTS=1 with real credentials")


@live
@skip_live
def test_live_tavily_search_and_stale_analysis():
    if not settings.tavily_api_key:
        pytest.skip("TAVILY_API_KEY not set")
    from vericode.tavily import TavilyClient
    out = TavilyClient().search("Python latest stable release python.org", include_domains=["python.org"], use_cache=False)
    assert out.ok and out.results and all(r.url.startswith("http") for r in out.results)
    r = stale.analyze("Python 3.12 is the latest stable version of Python.", mode="live")
    assert r["summary"]["evidence_mode"] == "live_tavily" and r["claims"][0]["evidence"]


@live
@skip_live
def test_live_llm_planner_and_coder(sample_project):
    if not llm.provider_status()["real"] or not llm.provider_status()["ready"]:
        pytest.skip("real LLM provider not configured")
    t = next(x for x in agent.load_catalog() if x["id"] == "users")
    r = agent.TaskRunner(agent.create_task(sample_project, t["prompt"], "vericode"), sample_project, t["prompt"], "vericode", 3,
                         acceptance=t["acceptance_tests"]).run()
    assert r["tokens"]["measurement"] == "ACTUAL_PROVIDER_USAGE" and "planner" in r["tokens"]["by_stage"]
