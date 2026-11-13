"""Regression tests for the adaptive execution path, the post-generation API audit, provider request-size handling
and the benchmark statistics (no network; MOCK provider or fake transports)."""
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from conftest import ROOT
from vericode import agent, api_audit, api_risk, benchmark, llm
from vericode.config import settings
from vericode.repo_intel import inspect_project

SAMPLE = ROOT / "demos" / "sample_project"
TS = ROOT / "demos" / "ts_project"
CATALOG = {t["id"]: t for t in json.loads((ROOT / "demos" / "tasks" / "catalog.json").read_text())}


# ------------------------------------------------------------------------------------------------ risk gate
@pytest.mark.parametrize("task_id", list(CATALOG))
def test_gate_matches_dataset_labels(task_id):
    t = CATALOG[task_id]
    project = ROOT / "demos" / t["project"]
    a = api_risk.assess(inspect_project(project), t["prompt"])
    assert a.risk == ("low" if t["api_risk"] == "none" else "high"), a.reasons


def test_gate_high_on_dependency_name_identifier_wording_and_no_tests(tmp_path):
    env = inspect_project(SAMPLE)
    assert api_risk.assess(env, "Use pydantic to add a field").risk == "high"
    assert api_risk.assess(env, "Subclass BaseModel for the export").risk == "high"
    assert api_risk.assess(env, "Upgrade the library call in storage").risk == "high"
    assert api_risk.assess(env, "Rename count_open to open_count in TaskStore").risk == "low"
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "app.py").write_text("def f():\n    return 1\n")
    a = api_risk.assess(inspect_project(bare), "Rename f to g")
    assert a.risk == "high" and "no test command" in a.reasons[0]


def test_gate_ignores_test_only_imports_unless_test_task():
    env = inspect_project(TS)
    assert "it" not in api_risk.third_party_imports(env, include_tests=False)
    assert "it" in api_risk.third_party_imports(env, include_tests=True)


# ------------------------------------------------------------------------------------------------ audit
def test_added_lines_only():
    assert api_audit.added_lines(None, "a\nb") is None
    assert api_audit.added_lines("a\nb\nc", "a\nB\nc\nd") == {2, 4}
    assert api_audit.added_lines("a", "a") == set()


def test_python_audit_flags_v1_pydantic_and_passes_v2(sample_project):
    env = inspect_project(SAMPLE)
    code = ("from pydantic import BaseModel, Field, validator, field_validator\n\n"
            "class U(BaseModel):\n    name: str = Field(regex='^a$')\n\n"
            "    @validator('name')\n    def v(cls, x):\n        return x\n\n"
            "    def pub(self):\n        return self.dict()\n\n"
            "    def pub2(self):\n        return self.model_dump()\n")
    found = {f["planned_api"]: f["status"] for f in api_audit.audit_python(env, "x.py", code, None)}
    assert found["pydantic.Field"] == "INCOMPATIBLE"
    assert found["pydantic.validator"] == "DEPRECATED"
    assert found["pydantic.BaseModel.dict"] == "DEPRECATED"
    assert found["pydantic.BaseModel.model_dump"] == "VERIFIED_LOCAL"
    assert "pydantic.field_validator" not in found  # imported but unused: bare imports are not audited


def test_python_audit_only_added_lines_and_ignores_stdlib_and_local(sample_project):
    env = inspect_project(SAMPLE)
    before = "from pydantic import BaseModel\n\nclass A(BaseModel):\n    def d(self):\n        return self.dict()\n"
    after = before + "\nimport os, json\nfrom taskboard import models\n\ndef e(a: A):\n    return a.model_dump()\n"
    fs = api_audit.audit_python(env, "x.py", after, api_audit.added_lines(before, after))
    assert [f["planned_api"] for f in fs] == []  # a.model_dump on a plain variable is unresolvable; old .dict() is not blamed


def test_typescript_audit_flags_deprecated_misspelled_and_bad_args(tmp_path):
    if not (TS / "node_modules").is_dir():
        pytest.skip("ts demo not installed")
    work = tmp_path / "ts"
    (work / "src").mkdir(parents=True)
    (work / "tsconfig.json").write_text((TS / "tsconfig.json").read_text())
    (work / "src" / "s.ts").write_text("import { z } from 'zod'\nexport const S = z.object({\n"
                                       "  a: z.string().nonempty(),\n  b: z.string().emial(),\n  c: z.string().min(3),\n})\n")
    env = inspect_project(TS)
    fs = api_audit.audit_typescript(type(env)(**{**env.__dict__, "root": str(work)}), [("src/s.ts", None)], deps_root=str(TS))
    by = {(f["line"], f["status"]) for f in fs}
    assert (3, "DEPRECATED") in by and (4, "NOT_FOUND") in by
    assert not any(f["line"] == 5 for f in fs)
    assert all(f["package"] == "zod" for f in fs)


# ------------------------------------------------------------------------------------------------ agent modes
def _run(task_id, mode):
    t = CATALOG[task_id]
    project = (ROOT / "demos" / t["project"]).resolve()
    tid = agent.create_task(project, t["prompt"], mode)
    return agent.TaskRunner(tid, project, t["prompt"], mode, 3, live=False, acceptance=t.get("acceptance_tests")).run()


def test_adaptive_fast_path_skips_planner_and_audits(sample_project):
    r = _run("summary", "vericode_adaptive")
    assert r["success"] and r["execution_path"] == "fast" and r["risk"]["risk"] == "low"
    assert "planner" not in r["tokens"]["by_stage"]
    assert r["api_audit"]["problem_count"] == 0
    assert "audit" in r["timings_s"]


def test_adaptive_full_path_keeps_preflight(sample_project):
    r = _run("users", "vericode_adaptive")
    assert r["execution_path"] == "full" and "planner" in r["tokens"]["by_stage"]


def test_full_and_context_only_configurations(sample_project):
    full = _run("summary", "vericode_full")
    assert full["execution_path"] == "full" and "planner" in full["tokens"]["by_stage"]
    ctx = _run("summary", "context_only")
    assert ctx["execution_path"] == "context_only" and "planner" not in ctx["tokens"]["by_stage"]
    assert "audit" not in ctx["timings_s"]  # no per-attempt audit in the ablation (final measurement audit only)


def test_vericode_alias_follows_setting(monkeypatch):
    monkeypatch.setattr(settings, "adaptive_execution", True)
    assert agent.resolve_mode("vericode") == "vericode_adaptive"
    monkeypatch.setattr(settings, "adaptive_execution", False)
    assert agent.resolve_mode("vericode") == "vericode_full"
    with pytest.raises(ValueError):
        agent.resolve_mode("turbo")


def test_audit_problem_forces_a_repair(sample_project, monkeypatch):
    """Tests pass but the code uses a deprecated API: the adaptive path repairs it (one extra coder call)."""
    t = CATALOG["summary"]
    calls = []
    real = llm.complete

    def fake(system, prompt, stage, task_id=None, max_tokens=4000, ledger=None, transport=None):
        calls.append(stage)
        if stage == "repair":  # the scripted mock has no repair script for this task: answer with the coder script
            stage = "coder"
        return real(system, prompt, stage, task_id, max_tokens, ledger, transport)

    monkeypatch.setattr(llm, "complete", fake)
    monkeypatch.setattr(agent, "audit_changes", lambda env, sb, ch, orig: {
        "findings": [], "summary": "1 problem",
        "problems": [{"planned_api": "pydantic.BaseModel.dict", "status": "DEPRECATED", "file": "taskboard/storage.py",
                      "line": 1, "explanation": "deprecated", "suggested_correction": "use model_dump"}]} if calls.count("coder") == 1 and calls.count("repair") == 0
        else {"findings": [], "problems": [], "summary": "ok"})
    project = (ROOT / "demos" / t["project"]).resolve()
    tid = agent.create_task(project, t["prompt"], "vericode_adaptive")
    r = agent.TaskRunner(tid, project, t["prompt"], "vericode_adaptive", 3, live=False, acceptance=t.get("acceptance_tests")).run()
    assert calls[:2] == ["coder", "repair"]
    assert r["attempts"][0]["passed"] and r["attempts"][0]["audit_problems"] == 1


# ------------------------------------------------------------------------------------------------ provider limits
@pytest.fixture
def groq(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "gsk-test-000000000000000000")
    monkeypatch.setattr(settings, "openai_base_url", "https://api.groq.com/openai/v1")
    monkeypatch.setattr(settings, "coder_model", "m")
    monkeypatch.setattr(settings, "planner_model", "m")
    monkeypatch.setattr(settings, "llm_stream", False)
    monkeypatch.setattr("time.sleep", lambda s: None)


TOO_LARGE = {"error": {"message": "Request too large for model `m` on tokens per minute (TPM): Limit 8000, Requested 9500, please reduce your message size", "type": "tokens", "code": "rate_limit_exceeded"}}


def test_413_retried_once_with_fitted_output_budget(groq):
    seen = []

    def h(req):
        body = json.loads(req.content)
        seen.append(body["max_tokens"])
        if len(seen) == 1:
            return httpx.Response(413, json=TOO_LARGE)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 5400, "completion_tokens": 20}})

    r = llm.complete("s", "p", "coder", max_tokens=4000, transport=httpx.MockTransport(h))
    assert r.text == "ok" and seen == [4000, 4000 - 1500 - 64]


def test_413_with_no_room_left_is_reported_not_retried(groq):
    seen = []
    big = json.loads(json.dumps(TOO_LARGE))
    big["error"]["message"] = big["error"]["message"].replace("Requested 9500", "Requested 11800")

    def h(req):
        seen.append(1)
        return httpx.Response(413, json=big)

    with pytest.raises(llm.LLMUnavailable, match="request too large"):
        llm.complete("s", "p", "coder", max_tokens=4000, transport=httpx.MockTransport(h))
    assert len(seen) == 1
    assert benchmark.classify({"success": False, "error": "LLMUnavailable: OpenAI HTTP 413: Request too large"}) == "BLOCKED"


# ------------------------------------------------------------------------------------------------ statistics
def _rec(task, rep, cfg, status="SUCCESS", tokens=1000, measurement="ACTUAL_PROVIDER_USAGE", **kw):
    return {"task": task, "rep": rep, "configuration": cfg, "status": status, "success": status == "SUCCESS",
            "first_pass_success": status == "SUCCESS", "repair_attempts": 0, "measurement": measurement,
            "input_tokens": tokens - 100, "output_tokens": 100, "total_tokens": tokens, "llm_calls": 1, "by_stage": {},
            "duration_s": 1.0, **kw}


def test_paired_savings_only_for_both_successful_same_label_and_negative_kept():
    recs = [_rec("t", 1, "baseline", tokens=1000), _rec("t", 1, "vericode_full", tokens=1500),
            _rec("t", 2, "baseline", tokens=1000), _rec("t", 2, "vericode_full", status="FAILED", tokens=200),
            _rec("t", 3, "baseline", status="BLOCKED", tokens=0, measurement=None), _rec("t", 3, "vericode_full", tokens=300),
            _rec("t", 4, "baseline", tokens=1000, measurement="ESTIMATED"), _rec("t", 4, "vericode_full", tokens=300)]
    s = benchmark.summarize(recs)
    comp = s["tasks"][0]["comparisons"]["vericode_full"]
    assert [p["rep"] for p in comp["pairs"]] == [1]
    assert comp["pairs"][0]["savings_pct"] == -50.0
    assert {e["rep"] for e in comp["excluded"]} == {2, 3, 4}
    assert s["tasks"][0]["configurations"]["baseline"]["measurement"] == "MIXED"
    assert s["overall"]["vericode_full"]["tasks_with_negative_savings"] == 1


def test_confidence_interval_only_from_five_pairs():
    assert benchmark.paired_stats([10, 20, 30])["ci95"] is None
    assert benchmark.paired_stats([10, 20, 30])["evidence"] == "exploratory"
    s = benchmark.paired_stats([10, 20, 30, 40, 50])
    assert s["ci95"] is not None and s["ci95"][0] < 30 < s["ci95"][1]
    assert benchmark.paired_stats([])["evidence"] == "none"


def test_plan_interleaves_rotates_and_skips_done():
    cat = [{"id": "a"}, {"id": "b"}]
    order = benchmark.plan_runs(cat, 2, ("baseline", "x", "y"), done={("a", 1, "x")})
    a = [(rep, cfg) for t, rep, cfg in order if t["id"] == "a"]
    assert a == [(1, "baseline"), (1, "y"), (2, "x"), (2, "y"), (2, "baseline")]


def test_resume_and_budget(tmp_path, sample_project, monkeypatch):
    path = tmp_path / "runs.jsonl"
    first = benchmark.run_benchmark(["summary"], runs=1, configurations=["baseline", "vericode_adaptive"], records_path=path)
    assert len(benchmark.load_records(path)) == 2
    calls = []
    monkeypatch.setattr(agent.TaskRunner, "run", lambda self: calls.append(1) or {})
    again = benchmark.run_benchmark(["summary"], runs=1, configurations=["baseline", "vericode_adaptive"], records_path=path)
    assert calls == [] and len(again["records"]) == 2  # nothing re-run
    capped = benchmark.run_benchmark(["summary"], runs=2, configurations=["baseline", "vericode_adaptive"], records_path=path, max_runs=0)
    blocked = [r for r in capped["records"] if r["status"] == "BLOCKED"]
    assert len(blocked) == 2 and all("run budget" in r["error"] for r in blocked) and calls == []
    assert first["measurement"] == "MOCK"


def test_blocked_run_stops_the_batch(tmp_path, sample_project, monkeypatch):
    monkeypatch.setattr(agent.TaskRunner, "run", lambda self: {"success": False, "error": "LLMUnavailable: openai: rate limited (HTTP 429)"})
    res = benchmark.run_benchmark(["summary"], runs=2, configurations=["baseline", "vericode_adaptive"], records_path=tmp_path / "r.jsonl")
    statuses = [r["status"] for r in res["records"]]
    assert statuses == ["BLOCKED"] * 4
    assert sum(1 for r in res["records"] if r.get("not_run")) == 3 and "provider blocked" in res["stopped"]


def test_published_results_endpoint(client, tmp_path, monkeypatch):
    from vericode import api
    d = tmp_path / "2026-11-13"
    d.mkdir()
    (d / "summary.json").write_text(json.dumps({"provider": "openai", "measurement_labels": ["ACTUAL_PROVIDER_USAGE"],
                                                "summary": {"tasks": [], "overall": {}}, "source_runs": [123]}))
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "summary.json").write_text("{not json")
    monkeypatch.setattr(api, "PUBLISHED_DIR", tmp_path)
    r = client.get("/api/benchmarks/published").json()["results"]
    assert [x["name"] for x in r] == ["2026-11-13"] and r[0]["source_runs"] == [123]


def test_audit_does_not_flag_model_fields_or_instance_attributes(sample_project):
    """Live batch 1 regression: self.sku inside a pydantic model was reported as pydantic.BaseModel.sku NOT_FOUND."""
    env = inspect_project(SAMPLE)
    code = ("from pydantic import BaseModel\n\nclass R(BaseModel):\n    sku: str\n    qty: int = 1\n\n"
            "    def payload(self):\n        self.cache = 1\n        return {'s': self.sku, 'q': self.qty, 'c': self.cache, 'x': self.helper()}\n\n"
            "    def legacy(self):\n        return self.dict()\n")
    fs = {f["planned_api"]: f["status"] for f in api_audit.audit_python(env, "r.py", code, None)}
    assert fs == {"pydantic.BaseModel.dict": "DEPRECATED"}


def test_413_numbers_kept_beyond_the_400_char_cut(groq):
    """Live batch 1 regression: Groq's long 413 body put 'Limit N, Requested M' past the truncated error text."""
    body = {"error": {"message": "Request too large for model `m` in organization `org_" + "x" * 420 + "` service tier `on_demand` "
                                 "on tokens per minute (TPM): Limit 8000, Requested 9100, please reduce your message size"}}
    seen = []

    def h(req):
        seen.append(json.loads(req.content)["max_tokens"])
        return httpx.Response(413, json=body) if len(seen) == 1 else httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5000, "completion_tokens": 9}})

    assert llm.complete("s", "p", "coder", max_tokens=4000, transport=httpx.MockTransport(h)).text == "ok"
    assert seen == [4000, 4000 - 1100 - 64]


def test_request_size_block_does_not_stop_the_batch(tmp_path, sample_project, monkeypatch):
    def fake(self):
        if self.mode == "baseline":
            return {"success": False, "error": "LLMUnavailable: openai HTTP 413: Request too large ... (request too large for this account tier)"}
        return {"success": True, "tokens": {"input": 10, "output": 5, "total": 15, "calls": 1, "by_stage": {}, "measurement": "MOCK"}}
    monkeypatch.setattr(agent.TaskRunner, "run", fake)
    res = benchmark.run_benchmark(["summary"], runs=2, configurations=["baseline", "vericode_adaptive"], records_path=tmp_path / "r.jsonl")
    assert res["stopped"] is None
    assert [r["status"] for r in res["records"] if r["configuration"] == "vericode_adaptive"] == ["SUCCESS", "SUCCESS"]


def test_drop_discards_records_for_rerun(tmp_path):
    from vericode import bench_cli
    path = tmp_path / "runs.jsonl"
    recs = [_rec("summary", 1, "baseline"), _rec("summary", 1, "vericode_adaptive"), _rec("inv_restock", 1, "vericode_adaptive")]
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))
    bench_cli.main(["--report-only", "--records", str(path), "--drop", "inv_restock:vericode_adaptive", "--tasks", "summary,inv_restock"])
    kept = benchmark.load_records(path)
    assert [(r["task"], r["configuration"]) for r in kept] == [("summary", "baseline"), ("summary", "vericode_adaptive")]
    assert len(benchmark.load_records(path.with_suffix(".dropped.jsonl"))) == 1


def test_load_records_keeps_last_record_per_run(tmp_path):
    path = tmp_path / "runs.jsonl"
    rows = [_rec("t", 1, "baseline", status="BLOCKED", tokens=0), _rec("t", 1, "x"), _rec("t", 1, "baseline", tokens=900)]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    recs = benchmark.load_records(path)
    assert len(recs) == 2 and next(r for r in recs if r["configuration"] == "baseline")["total_tokens"] == 900


def test_provider_account_ids_are_redacted():
    from vericode.security import redact
    assert redact("in organization `org_01m6vgesmhe2xs91b47gjn77c8` service") == "in organization `org_[redacted]` service"
