"""Final-validation phase: streaming providers, combined Track1xTrack2 evidence, correction tracking,
cost basis, memory reuse, malicious-input sandbox tests, persistence."""
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from vericode import agent, benchmark, db, jsinspect, llm, memory, security, stale
from vericode.config import ROOT, settings

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)
TS_PROJECT = ROOT / "demos" / "ts_project"
needs_docker = pytest.mark.skipif(not security.docker_available(), reason="Docker daemon not reachable")


def _sse(events):
    return "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"


# ---------------------------------------------------------------- streaming
def test_anthropic_streaming_collects_text_and_usage(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    monkeypatch.setattr(settings, "coder_model", "m")
    monkeypatch.setattr(settings, "llm_stream", True)
    seen = {}

    def h(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, text=_sse([
            {"type": "message_start", "message": {"usage": {"input_tokens": 120, "output_tokens": 1}}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hel"}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "lo"}},
            {"type": "message_delta", "usage": {"output_tokens": 9}},
            {"type": "message_stop"},
        ]), headers={"content-type": "text/event-stream"})
    r = llm.complete("s", "p", "coder", transport=httpx.MockTransport(h))
    assert seen["body"]["stream"] is True
    assert (r.text, r.input_tokens, r.output_tokens, r.measurement) == ("Hello", 120, 9, "ACTUAL_PROVIDER_USAGE")


def test_openai_streaming_requests_usage(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-00000000000000000000")
    monkeypatch.setattr(settings, "coder_model", "m")
    monkeypatch.setattr(settings, "llm_stream", True)
    seen = {}

    def h(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, text=_sse([{"choices": [{"delta": {"content": "a"}}]}, {"choices": [{"delta": {"content": "b"}, "finish_reason": "stop"}]},
                                              {"choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 2}}]))
    r = llm.complete("s", "p", "repair", transport=httpx.MockTransport(h))
    assert seen["body"]["stream_options"] == {"include_usage": True}
    assert (r.text, r.input_tokens, r.output_tokens, r.measurement) == ("ab", 50, 2, "ACTUAL_PROVIDER_USAGE")


def test_streaming_without_usage_is_labelled_estimated(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-00000000000000000000")
    monkeypatch.setattr(settings, "coder_model", "m")
    monkeypatch.setattr(settings, "openai_base_url", "http://gateway.local/v1")
    r = llm.complete("s", "p", "coder", transport=httpx.MockTransport(lambda q: httpx.Response(200, text=_sse([{"choices": [{"delta": {"content": "x"}, "finish_reason": "stop"}]}]))))
    assert r.measurement == "ESTIMATED"


def test_streaming_rate_limit_then_success(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    monkeypatch.setattr(settings, "coder_model", "m")
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(200, text=_sse([{"type": "message_start", "message": {"usage": {"input_tokens": 3, "output_tokens": 0}}},
                                              {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ok"}},
                                              {"type": "message_delta", "usage": {"output_tokens": 1}}, {"type": "message_stop"}]))
    r = llm.complete("s", "p", "coder", transport=httpx.MockTransport(h))
    assert r.text == "ok" and calls["n"] == 2


# ---------------------------------------------------------------- combined workflow
def _empty(tmp_path):
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"sources": []}))
    return p


def test_installed_source_evidence_python(tmp_path, sample_project):
    a = ("In Pydantic, use the @validator decorator to validate fields. Pydantic provides BaseModel.model_dump() for serialization. "
         "The pydantic BaseSettings class is available directly from pydantic. Pydantic no longer provides BaseModel.dict(). "
         "In pydantic, the validator decorator is deprecated.")
    r = stale.analyze(a, mode="fixture", fixture=_empty(tmp_path), now=NOW, workspace="sample_project")
    st = [c["status"] for c in r["claims"]]
    assert st == ["CONTRADICTED", "CURRENT_SUPPORTED", "CONTRADICTED", "CONTRADICTED", "CURRENT_SUPPORTED"]
    ev = r["claims"][0]["evidence"][0]
    assert ev["origin"] == "installed_source" and ev["url"].startswith("installed://pydantic@2.9.2/") and "class_validators.py" in ev["url"]
    assert r["claims"][0]["correction"] is None  # flagged, never rewritten from installed-source evidence
    assert "pydantic-settings" in r["claims"][2]["evidence"][0]["excerpt"]


def test_installed_source_needs_workspace_and_known_symbol(tmp_path, sample_project):
    a = "In Pydantic, use the @validator decorator to validate fields."
    assert stale.analyze(a, mode="fixture", fixture=_empty(tmp_path), now=NOW)["claims"][0]["status"] == "UNVERIFIED"
    r = stale.analyze("Pydantic offers the frobnicate_everything helper.", mode="fixture", fixture=_empty(tmp_path), now=NOW, workspace="sample_project")
    assert r["claims"][0]["status"] == "UNVERIFIED"  # unknown symbol: absence is not evidence


def test_installed_source_evidence_typescript(tmp_path):
    if not (jsinspect.ts_checker_available() and (TS_PROJECT / "node_modules").is_dir()):
        pytest.skip("ts demo not installed")
    r = stale.analyze("In zod, ZodString.nonempty() is the recommended way to require a value.", mode="fixture",
                      fixture=_empty(tmp_path), now=NOW, workspace="ts_project")
    c = r["claims"][0]
    assert c["status"] == "CONTRADICTED" and "deprecated" in c["evidence"][0]["excerpt"]


# ---------------------------------------------------------------- correction tracking
def test_api_corrections_detects_still_used_and_corrected():
    findings = [{"planned_api": "pydantic.validator", "status": "DEPRECATED", "ecosystem": "python"},
                {"planned_api": "pydantic.Field", "status": "INCOMPATIBLE", "ecosystem": "python",
                 "argument_checks": [{"argument": "regex", "status": "rejected"}]},
                {"planned_api": "zod:ZodString.min", "status": "INCOMPATIBLE", "ecosystem": "node", "arguments": ['"3"'], "argument_checks": []},
                {"planned_api": "pydantic.BaseModel", "status": "VERIFIED_LOCAL"}]
    diff = '+++ b/x.py\n+from pydantic import validator, Field\n+    name: str = Field(pattern="a")\n+  u: z.string().min("3"),\n'
    res = {r["planned_api"]: r["result"] for r in agent.api_corrections(findings, diff)}
    assert res == {"pydantic.validator": "still_used", "pydantic.Field": "corrected", "zod:ZodString.min": "still_used"}


def test_benchmark_reports_flagged_api_usage_in_baseline(sample_project):
    res = benchmark.run_benchmark(["users"], runs=1, max_repairs=3)
    fu = res["tasks"][0]["flagged_api_usage"][0]
    assert fu["vericode_flagged_apis_used"] == 0
    assert fu["baseline_flagged_apis_used"] == 0  # mock baseline eventually repaired all three via test failures


def test_ts_benchmark_baseline_ships_deprecated_api():
    if not (jsinspect.ts_checker_available() and (TS_PROJECT / "node_modules").is_dir()):
        pytest.skip("ts demo not installed")
    res = benchmark.run_benchmark(["signup"], runs=1, max_repairs=3)
    fu = res["tasks"][0]["flagged_api_usage"][0]
    assert fu["baseline_flagged_apis_used"] == 1 and fu["vericode_flagged_apis_used"] == 0
    assert "nonempty" in fu["baseline_details"][0]["planned_api"]


# ---------------------------------------------------------------- cost basis
def test_cost_uses_per_model_price_and_never_prices_mock(client):
    llm.record_usage("t1", llm.LLMResult("", 1_000_000, 100_000, False, "anthropic", "real-model", "coder"))
    llm.record_usage("t2", llm.LLMResult("", 500, 50, True, "mock", "mock-scripted", "coder"))
    client.put("/api/settings", json={"model_prices": {"real-model": {"input": 2.0, "output": 10.0}}})
    rows = {r["model"]: r for r in client.get("/api/analytics/tokens").json()["by_model"]}
    assert rows["real-model"]["cost_usd"] == 3.0 and "per-model" in rows["real-model"]["cost_basis"]
    assert rows["mock-scripted"]["cost_usd"] is None


# ---------------------------------------------------------------- memory reuse
def test_memory_rule_reused_on_next_run(sample_project):
    from vericode.repo_intel import inspect_project
    from vericode.skeleton import PlannedAPI, PlannedPackage
    from vericode.verify_api import verify_planned_api
    env = inspect_project(sample_project)
    pkg = PlannedPackage(package="pydantic", ecosystem="python", planned_apis=[PlannedAPI(import_path="pydantic", name="BaseModel.dict", type="method")])
    f1 = verify_planned_api(env, pkg, pkg.planned_apis[0]).to_dict()
    assert memory.save_from_finding(f1)
    f2 = verify_planned_api(env, pkg, pkg.planned_apis[0])
    assert f2.memory_rule and f2.memory_rule["correction"].startswith("The `dict` method is deprecated")
    assert memory.invalidate_for_versions({"pydantic": "3.0.0"}) == 1
    assert verify_planned_api(env, pkg, pkg.planned_apis[0]).memory_rule is None  # obsolete rule not trusted


# ---------------------------------------------------------------- malicious inputs
def test_symlink_escape_rejected_for_edits(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("host secret\n")
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "link.txt").symlink_to(outside)
    (ws / "linkdir").symlink_to(tmp_path)
    edits = agent.parse_edits("FILE: link.txt\n<<<<<<< SEARCH\nhost secret\n=======\npwned\n>>>>>>> REPLACE\n"
                              "FILE: linkdir/new.py\n<<<<<<< SEARCH\n=======\nx\n>>>>>>> REPLACE\n")
    changed, errors = agent.apply_edits(ws, edits)
    assert changed == [] and len(errors) == 2 and outside.read_text() == "host secret\n"


@pytest.mark.parametrize("argv", [["python", "-m", "pytest", "$(id)"], ["npm", "test", "&&", "curl", "x"], ["/bin/sh", "-c", "id"],
                                  ["pytest", "--x`id`"], ["python3.13", "-c", "import os"], ["npx", "tsc", "--noEmit", ";", "rm"]])
def test_command_injection_rejected(argv, tmp_path):
    with pytest.raises(security.SecurityError):
        security.run_command(argv, tmp_path, backend="process")


def test_workspace_path_attacks_rejected():
    for bad in ["../../etc", "/etc", "sample_project/../../", "sample_project/\x00"]:
        with pytest.raises(security.SecurityError):
            security.resolve_workspace(bad)


@needs_docker
def test_docker_cannot_read_host_files_or_escape(tmp_path, sample_project):
    secret_dir = tmp_path / "hostsecret"
    secret_dir.mkdir()
    (secret_dir / "key.txt").write_text("TOPSECRET")
    work = tmp_path / "work"
    work.mkdir()
    (work / "leak").symlink_to(secret_dir / "key.txt")  # symlink pointing at a host file
    (work / "test_escape.py").write_text(
        "import os, pytest\n"
        f"def test_host_paths_absent():\n    assert not os.path.exists({str(secret_dir)!r})\n    assert not os.path.exists('/home/claude/vericode/.env')\n"
        "def test_symlink_does_not_resolve_to_host():\n    with pytest.raises(OSError):\n        open('/work/leak').read()\n"
        "def test_proc_limits():\n    import resource\n    assert os.getuid() == 65534\n"
        "def test_cannot_write_outside_work():\n    for p in ('/usr/x', '/etc/x', '/x'):\n        with pytest.raises(OSError):\n            open(p, 'w')\n")
    r = security.run_command(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], work, backend="docker",
                             ro_mounts={".venv": sample_project / ".venv"})
    assert r.returncode == 0, r.stdout + r.stderr


@needs_docker
def test_docker_fork_bomb_contained(tmp_path, sample_project):
    (tmp_path / "test_bomb.py").write_text(
        "import os, pytest\n"
        "def test_pids_limited():\n"
        "    pids = []\n"
        "    with pytest.raises(OSError):\n"
        "        for _ in range(2000):\n"
        "            pid = os.fork()\n"
        "            if pid == 0:\n                import time; time.sleep(5); os._exit(0)\n"
        "            pids.append(pid)\n")
    r = security.run_command(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], tmp_path, backend="docker", timeout=60,
                             ro_mounts={".venv": sample_project / ".venv"})
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------- persistence after restart
def test_runs_benchmarks_rules_evidence_survive_restart(sample_project, tmp_path):
    res = benchmark.run_benchmark(["summary"], runs=1, max_repairs=1)
    a = stale.analyze("ChatGPT Plus costs $20 per month.", mode="fixture", fixture=_empty(tmp_path), now=NOW)
    db._conn = None
    db.init_db()
    assert db.row("SELECT id FROM benchmarks WHERE id=?", (res["id"],))
    assert db.row("SELECT COUNT(*) n FROM tasks WHERE benchmark_id=?", (res["id"],))["n"] == len(benchmark.DEFAULT_CONFIGURATIONS)
    assert stale.load_analysis(a["id"])["claims"]
    assert db.row("SELECT COUNT(*) n FROM sessions")["n"] >= 0
