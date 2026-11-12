"""Regression tests for API edge cases found by input probing (each used to return a 500, leak state or misbehave)."""
import subprocess
import sys

import pytest

from conftest import ROOT


def test_verify_api_invalid_identifier_is_422_not_500(client):
    for body in ({"path": "sample_project", "package": "", "import_path": "", "name": ""},
                 {"path": "sample_project", "package": "pydantic", "import_path": "pydantic", "name": "a b"}):
        r = client.post("/api/verify-api", json=body)
        assert r.status_code == 422, r.text
        assert isinstance(r.json()["detail"], list)


def test_failed_preflight_marks_task_failed_not_queued(client):
    from vericode import db
    r = client.post("/api/preflight", json={"path": "sample_project", "task": "an arbitrary task the mock cannot do", "live": False})
    assert r.status_code == 503
    rows = db.rows("SELECT status, success, result_json FROM tasks WHERE mode='preflight'")
    assert len(rows) == 1
    assert rows[0]["status"] == "failed" and rows[0]["success"] == 0
    assert "MOCK_PROVIDER_NO_SCRIPT" in db.loads(rows[0]["result_json"])["error"]


@pytest.mark.parametrize("url", ["/api/tasks?limit=-1", "/api/evidence?limit=-1", "/api/tasks?limit=0"])
def test_non_positive_limit_is_clamped(client, url):
    from vericode import db
    with db.tx() as c:
        for i in range(3):
            c.execute("INSERT INTO tasks(id, project_path, prompt, mode, status, created_at) VALUES(?,?,?,?,?,?)",
                      (f"t{i}", "p", "x", "baseline", "succeeded", float(i)))
    r = client.get(url)
    assert r.status_code == 200
    if url.startswith("/api/tasks"):
        assert len(r.json()) == 1  # SQLite treats LIMIT -1 as "no limit"; the API must not


def test_benchmark_rejects_unknown_task_ids(client):
    r = client.post("/api/benchmarks", json={"task_ids": ["nope"], "runs": 1, "live": False})
    assert r.status_code == 400 and "nope" in r.json()["detail"]


def test_benchmark_slot_is_claimed_before_the_thread_starts(client, monkeypatch):
    from vericode import api

    class NeverStarts:  # the worker never runs, so only the request handler can have claimed the slot
        def __init__(self, *a, **k): ...
        def start(self): ...

    monkeypatch.setattr(api, "threading", type("T", (), {"Thread": NeverStarts}))  # only the api module's view
    try:
        assert client.post("/api/benchmarks", json={"task_ids": ["users"], "runs": 1, "live": False}).status_code == 200
        assert client.post("/api/benchmarks", json={"task_ids": ["users"], "runs": 1, "live": False}).status_code == 409
    finally:
        api._bench_state["running"] = False


@pytest.mark.parametrize("module", ["vericode.demo", "vericode.live_validation"])
def test_cli_rejects_zero_runs(module, tmp_path):
    args = [sys.executable, "-m", module] + (["3"] if module == "vericode.demo" else []) + ["--runs", "0"]
    p = subprocess.run(args, cwd=ROOT / "backend", capture_output=True, text=True, timeout=60,
                       env={"PATH": "/usr/bin:/bin", "VERICODE_DB": str(tmp_path / "x.db"), "VERICODE_LLM_PROVIDER": "mock"})
    assert p.returncode == 2 and "--runs must be between 1 and 10" in p.stderr
