import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vericode import agent, benchmark, db, llm, memory
from vericode.agent import TaskRunner, apply_edits, create_task, load_catalog, parse_edits, summarize_ledger
from vericode.config import settings
from vericode.security import SecurityError, check_public_url, redact, run_command, safe_join
from vericode.skeleton import extract_json, generate_skeleton


def catalog(tid):
    return next(t for t in load_catalog() if t["id"] == tid)


def run_cat(sample_project, tid, mode, repairs=3):
    t = catalog(tid)
    task = create_task(sample_project, t["prompt"], mode)
    return TaskRunner(task, sample_project, t["prompt"], mode, repairs, acceptance=t["acceptance_tests"]).run(), task


# ---------------------------------------------------------------- coding agent
def test_vericode_detects_incompatibility_and_passes_first_time(sample_project):
    r, tid = run_cat(sample_project, "users", "vericode")
    assert r["success"] and r["first_pass_success"] and r["repair_attempts"] == 0
    assert "pattern=" in r["diff"] and "field_validator" in r["diff"] and "model_dump" in r["diff"]
    pf = db.loads(db.row("SELECT preflight_json FROM tasks WHERE id=?", (tid,))["preflight_json"])
    statuses = {f["planned_api"]: f["status"] for f in pf["findings"]}
    assert statuses["pydantic.Field"] == "INCOMPATIBLE" and statuses["pydantic.validator"] == "DEPRECATED"
    assert "PRE-FLIGHT BRIEFING" in pf["briefing"]
    assert not (sample_project / "taskboard" / "users.py").exists()  # real workspace untouched until apply


def test_baseline_needs_repairs_and_uses_more_tokens(sample_project):
    b, _ = run_cat(sample_project, "users", "baseline")
    v, _ = run_cat(sample_project, "users", "vericode")
    assert b["success"] and not b["first_pass_success"] and b["repair_attempts"] == 3
    assert v["tokens"]["total"] < b["tokens"]["total"]
    assert "planner" in v["tokens"]["by_stage"]  # overhead counted
    assert v["tokens"]["measurement"] == "MOCK"


def test_existing_file_modification_targeted(sample_project):
    r, _ = run_cat(sample_project, "summary", "vericode")
    assert r["success"] and r["changed_files"] == ["taskboard/storage.py"]
    assert r["diff"].count("\n+") < 15 and "-class TaskStore" not in r["diff"]


def test_max_retry_enforced(sample_project):
    r, _ = run_cat(sample_project, "users", "baseline", repairs=1)
    assert not r["success"] and len(r["attempts"]) == 2 and r["repair_attempts"] == 1


def test_unknown_task_with_mock_fails_explicitly(sample_project):
    tid = create_task(sample_project, "Refactor billing to use money library", "vericode")
    r = TaskRunner(tid, sample_project, "Refactor billing to use money library", "vericode", 1).run()
    assert not r["success"] and "MOCK_PROVIDER_NO_SCRIPT" in r["error"]


def test_apply_changes_with_overwrite_protection(sample_project, tmp_path, monkeypatch):
    proj = tmp_path / "ws" / "proj"
    shutil.copytree(sample_project, proj, symlinks=True, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
    (proj / ".venv").symlink_to(sample_project / ".venv")
    monkeypatch.setattr(agent, "RUNS_DIR", tmp_path / "runs")
    t = catalog("summary")
    tid = create_task(proj, t["prompt"], "vericode")
    TaskRunner(tid, proj, t["prompt"], "vericode", 1, acceptance=t["acceptance_tests"]).run()
    (proj / "taskboard" / "storage.py").write_text((proj / "taskboard" / "storage.py").read_text() + "\n# user edit\n")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        agent.apply_changes(tid)
    tid2 = create_task(proj, t["prompt"], "vericode")
    TaskRunner(tid2, proj, t["prompt"], "vericode", 1, acceptance=t["acceptance_tests"]).run()
    assert agent.apply_changes(tid2)["applied"] == ["taskboard/storage.py"]
    assert "priority_summary" in (proj / "taskboard" / "storage.py").read_text()


def test_edit_parsing_and_safety(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\ny = 2\n")
    edits = parse_edits("FILE: a.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 10\n>>>>>>> REPLACE\n"
                        "FILE: ../evil.py\n<<<<<<< SEARCH\n=======\nboom\n>>>>>>> REPLACE\n"
                        "FILE: a.py\n<<<<<<< SEARCH\n=======\noverwrite\n>>>>>>> REPLACE\n")
    changed, errors = apply_edits(tmp_path, edits)
    assert (tmp_path / "a.py").read_text() == "x = 10\ny = 2\n"
    assert changed == ["a.py"] and len(errors) == 2
    assert any("escapes" in e for e in errors) and any("refusing to overwrite" in e for e in errors)


def test_syntax_error_detected_by_checks(sample_project, tmp_path):
    sb = agent.make_sandbox(sample_project, "syntax_test")
    (sb / "taskboard" / "storage.py").write_text("def broken(:\n")
    from vericode.repo_intel import inspect_project
    checks = agent.run_checks(sb, inspect_project(sample_project))
    assert not checks["passed"] and "SyntaxError" in agent.failure_digest(checks)
    shutil.rmtree(sb)


# ---------------------------------------------------------------- skeleton
def test_skeleton_schema_rejection_and_bounded_retry(monkeypatch):
    outputs = iter(["not json", '{"packages":[{"package":"x","ecosystem":"cobol","planned_apis":[]}]}',
                    '{"packages":[{"package":"x","ecosystem":"python","planned_apis":[{"import_path":"x","name":"y","type":"function"}]}]}'])

    def fake(system, prompt, stage, task_id=None, max_tokens=0, ledger=None):
        r = llm.LLMResult(next(outputs), 10, 5, True, "mock", "m", stage)
        ledger.append(r)
        return r
    monkeypatch.setattr(llm, "complete", fake)
    ledger = []
    sk, errs = generate_skeleton("t", "", "", None, ledger)
    assert sk.packages[0].planned_apis[0].name == "y" and len(errs) == 2 and len(ledger) == 3
    outputs2 = iter(["bad"] * 3)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (k["ledger"].append(llm.LLMResult(next(outputs2), 1, 1, True, "m", "m", "planner")), k["ledger"][-1])[1])
    with pytest.raises(ValueError, match="bounded retries"):
        generate_skeleton("t", "", "", None, [])


def test_extract_json_from_fence():
    assert extract_json('text ```json\n{"a": {"b": 1}}\n``` more') == {"a": {"b": 1}}


# ---------------------------------------------------------------- tokens
def test_token_aggregation_and_separation():
    L = [llm.LLMResult("", 100, 20, False, "anthropic", "m", "planner"),
         llm.LLMResult("", 1000, 300, False, "anthropic", "m", "coder"),
         llm.LLMResult("", 500, 50, False, "anthropic", "m", "repair")]
    s = summarize_ledger(L)
    assert (s["input"], s["output"], s["total"], s["calls"]) == (1600, 370, 1970, 3)
    assert s["by_stage"]["planner"] == {"input": 100, "output": 20, "calls": 1}
    assert s["measurement"] == "ACTUAL_PROVIDER_USAGE"
    L.append(llm.LLMResult("", 10, 10, True, "mock", "m", "repair"))
    assert summarize_ledger(L)["measurement"] == "MOCK"


def test_usage_recorded_per_stage():
    llm.complete("sys", "TASK:\nAdd a priority_summary() method", stage="planner", task_id="t1")
    rows = db.rows("SELECT * FROM token_usage WHERE task_id='t1'")
    assert rows[0]["stage"] == "planner" and rows[0]["estimated"] == 1 and rows[0]["input_tokens"] > 0


def test_benchmark_savings_only_when_both_succeed(sample_project):
    res = benchmark.run_benchmark(["users", "summary"], runs=1, max_repairs=3)
    by = {t["task"]: t for t in res["tasks"]}
    for t in by.values():
        assert t["savings_valid"] and t["token_savings_pct"] > 0
        b, v = t["summary"]["baseline"]["total_tokens"]["mean"], t["summary"]["vericode"]["total_tokens"]["mean"]
        assert t["token_savings_pct"] == round((b - v) / b * 100, 1)
    assert by["users"]["detection"]["detection_rate"] == 1.0 and by["users"]["detection"]["false_positive_rate"] == 0.0
    res2 = benchmark.run_benchmark(["users"], runs=1, max_repairs=1)
    assert res2["tasks"][0]["token_savings_pct"] is None and "unfair" in res2["tasks"][0]["savings_note"]


# ---------------------------------------------------------------- security
def test_safe_join_rejects_traversal(tmp_path):
    for bad in ["../x", "/etc/passwd", ".git/config", ".env", "a/../../b", "node_modules/x/index.js"]:
        with pytest.raises(SecurityError):
            safe_join(tmp_path, bad)


def test_command_allowlist(tmp_path):
    for bad in [["rm", "-rf", "/"], ["python", "-c", "print(1)"], ["npm", "install", "x"], ["pytest", ";", "ls"]]:
        with pytest.raises(SecurityError):
            run_command(bad, tmp_path)


def test_command_env_scrubbed_and_timeout(tmp_path, monkeypatch, sample_project):
    (tmp_path / ".venv").symlink_to(sample_project / ".venv")  # project interpreter with pytest (CI python lacks it)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-SECRETSECRET123")
    (tmp_path / "test_env.py").write_text("import os, time\ndef test_env():\n    assert 'TAVILY_API_KEY' not in os.environ\n")
    r = run_command(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], tmp_path)
    assert r.returncode == 0, r.stdout
    (tmp_path / "test_env.py").write_text("import time\ndef test_slow():\n    time.sleep(10)\n")
    r = run_command(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], tmp_path, timeout=2)
    assert r.timed_out


def test_redaction(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-abcdefghijkl")
    assert "abcdefghijkl" not in redact("key tvly-abcdefghijkl and sk-ant-api03-zzzzzzzzzz and password=hunter2hunter2")


def test_ssrf_guard():
    for bad in ["http://localhost/", "http://10.0.0.5/", "http://169.254.169.254/latest", "ftp://x.com/", "http://user:pw@example.com/"]:
        with pytest.raises(SecurityError):
            check_public_url(bad)


# ---------------------------------------------------------------- memory
def test_memory_only_verified_rules_and_version_invalidation(sample_project, tmp_path):
    f_ok = {"status": "DEPRECATED", "suggested_correction": "use model_dump", "verification_confidence": "high",
            "local": {"location": "pydantic/main.py:1104"}, "installed_version": "2.9.2", "package": "pydantic",
            "planned_api": "pydantic.BaseModel.dict", "explanation": "deprecated"}
    assert memory.save_from_finding(dict(f_ok, verification_confidence="medium")) is None  # unverified -> rejected
    assert memory.save_from_finding(dict(f_ok, status="UNCERTAIN")) is None
    r = memory.save_from_finding(f_ok)
    assert r and memory.find_rule("pydantic", "2.9.2", "BaseModel.dict")
    assert memory.find_rule("pydantic", "2.10.0", "BaseModel.dict") is None
    assert memory.invalidate_for_versions({"pydantic": "2.10.0"}) == 1
    memory.update_rule(r["id"], {"active": 1})
    proj = tmp_path / "p"
    proj.mkdir()
    (proj / ".agent-rules.md").write_text("# My rules\n- keep functions small\n")
    memory.export_rules(proj)
    memory.export_rules(proj)
    text = (proj / ".agent-rules.md").read_text()
    assert text.startswith("# My rules") and text.count("vericode:rules:start") == 1 and "model_dump" in text


# ---------------------------------------------------------------- API contract
def test_api_end_to_end(sample_project, client):
    c = client
    assert c.get("/api/health").json()["ok"]
    s = c.get("/api/settings").json()
    assert "tavily_api_key" not in str(s) and s["tavily_configured"] is False
    assert c.put("/api/settings", json={"tavily_api_key": "x"}).status_code == 400
    assert c.post("/api/projects/inspect", json={"path": "/etc"}).status_code == 400
    env = c.post("/api/projects/inspect", json={"path": "sample_project"}).json()
    assert any(d["name"] == "pydantic" and d["installed"] == "2.9.2" for d in env["dependencies"])
    pf = c.post("/api/preflight", json={"path": "sample_project", "task": catalog("users")["prompt"], "live": True}).json()
    assert {f["status"] for f in pf["findings"]} >= {"INCOMPATIBLE", "DEPRECATED"}
    assert all(f["live"]["status"] == "missing_key" for f in pf["findings"] if f["live"])
    v = c.post("/api/verify-api", json={"path": "sample_project", "package": "pydantic", "import_path": "pydantic", "name": "BaseSettings", "type": "class"}).json()
    assert v["status"] == "NOT_FOUND"
    a = c.post("/api/stale/analyze", json={"answer": c.get("/api/stale/demo").json()["answer"], "mode": "fixture"}).json()
    assert a["summary"]["evidence_mode"] == "fixture"
    assert c.post(f"/api/stale/{a['id']}/correct").json()["changes"]
    assert c.get(f"/api/evidence?analysis_id={a['id']}").json()
    assert c.post("/api/stale/analyze", json={"answer": "x" * 30000}).status_code == 422
    assert c.get("/api/dashboard").json()["claims_checked"] == 6
    assert c.get("/api/tasks/nope").status_code == 404
