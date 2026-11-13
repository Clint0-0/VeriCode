"""Regression tests for the Coding Workspace WinError 2 failure (process sandbox command launch).

Root cause: run_command() passed ["npm", "test"] straight to subprocess.run (list form, no shell). On Windows
CreateProcess does not apply PATHEXT, so `npm` (really npm.cmd) was not found -> FileNotFoundError [WinError 2],
raised right after the CODER stage and shown as a bare traceback. Fake executables keep these tests machine-independent."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from conftest import ROOT
from vericode import agent, security
from vericode.security import SecurityError, child_env, resolve_executable, run_command

WIN = os.name == "nt"


def fake_tool(bindir: Path, name: str, body_sh: str, body_cmd: str) -> Path:
    """An executable `name` in bindir: npm.cmd on Windows (like real Node installs), a shell script elsewhere."""
    bindir.mkdir(parents=True, exist_ok=True)
    if WIN:
        p = bindir / f"{name}.cmd"
        p.write_text(f"@echo off\r\n{body_cmd}\r\n")
    else:
        p = bindir / name
        p.write_text(f"#!/bin/sh\n{body_sh}\n")
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


@pytest.fixture
def ws(tmp_path):
    d = tmp_path / "work space" / "proj"  # path with spaces
    d.mkdir(parents=True)
    return d


@pytest.fixture
def bindir(tmp_path, monkeypatch):
    b = tmp_path / "tool bin"  # PATH entry with a space
    monkeypatch.setenv("PATH", str(b) + os.pathsep + os.environ.get("PATH", ""))
    return b


# --------------------------------------------------------------------------------------------- resolution
def test_resolves_wrapper_by_bare_name_root_cause(bindir):
    """`npm` must resolve to the real file (npm.cmd on Windows) - the exact step that was missing."""
    tool = fake_tool(bindir, "npm", "exit 0", "exit /b 0")
    got = resolve_executable("npm", os.environ["PATH"])
    assert got and Path(got).resolve() == tool.resolve()


def test_launch_uses_resolved_absolute_path(ws, bindir, monkeypatch):
    tool = fake_tool(bindir, "npm", "exit 0", "exit /b 0")
    seen = {}

    def spy(cmd, **kw):
        seen["cmd"], seen["cwd"] = cmd, kw["cwd"]
        raise FileNotFoundError(2, "should not get here")
    monkeypatch.setattr(security, "network_isolation_available", lambda: False)
    monkeypatch.setattr(security.subprocess, "run", spy)
    r = run_command(["npm", "test"], ws, backend="process")
    assert Path(seen["cmd"][0]).resolve() == tool.resolve() and seen["cmd"][1:] == ["test"]
    assert Path(seen["cwd"]) == ws.absolute()
    assert r.error["category"] == "launch_failed"  # an OS refusal is structured too, never an unhandled exception


# --------------------------------------------------------------------------------------------- outcomes
@pytest.mark.parametrize("isolated", [False, True])
def test_success_with_spaces(ws, bindir, monkeypatch, isolated):
    if isolated and not security.network_isolation_available():
        pytest.skip("unshare not available here")
    monkeypatch.setattr(security, "network_isolation_available", lambda: isolated)
    fake_tool(bindir, "npm", 'echo "ran $1 in $(pwd)"', "echo ran %1 in %CD%")
    r = run_command(["npm", "test"], ws, backend="process")
    assert r.returncode == 0 and r.error is None, r.stderr
    assert "ran test in" in r.stdout and "work space" in r.stdout


def test_nonzero_exit_code_preserved(ws, bindir):
    fake_tool(bindir, "npm", "echo boom >&2; exit 3", "echo boom 1>&2\r\nexit /b 3")
    r = run_command(["npm", "test"], ws, backend="process")
    assert r.returncode == 3 and "boom" in r.stderr and r.error is None  # a test failure, not a launch error


@pytest.mark.skipif(WIN, reason="timeout of a .cmd wrapper leaves the grandchild running on Windows; covered on POSIX")
def test_timeout_preserved(ws, bindir):
    fake_tool(bindir, "npm", "sleep 5", "")
    r = run_command(["npm", "test"], ws, backend="process", timeout=1)
    assert r.timed_out and r.returncode == -1 and r.error is None


def test_missing_executable_is_structured(ws, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(security, "network_isolation_available", lambda: False)
    r = run_command(["npm", "test"], ws, backend="process")  # used to raise FileNotFoundError
    assert r.returncode == 127 and r.error["category"] == "executable_not_found"
    assert "Node.js" in r.error["action"] and r.error["details"]["cwd_exists"] is True
    assert r.error["details"]["executable"] == "npm" and r.error["details"]["os"]


def test_missing_workspace_is_structured(tmp_path):
    r = run_command(["npm", "test"], tmp_path / "gone", backend="process")
    assert r.error["category"] == "workspace_missing" and r.error["details"]["cwd_exists"] is False


def test_allowlist_still_enforced(ws):
    with pytest.raises(SecurityError):
        run_command(["npm", "install", "evil"], ws, backend="process")


@pytest.mark.skipif(not WIN, reason="cmd.exe wrapper quoting only applies on Windows")
def test_batch_unsafe_characters_rejected(ws, bindir):
    fake_tool(bindir, "pytest", "", "exit /b 0")
    with pytest.raises(SecurityError):
        run_command(["pytest", "-k", "%PATH%"], ws, backend="process")


def test_child_env_has_no_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-secret")
    env = child_env(EXTRA="1")
    assert "OPENAI_API_KEY" not in env and "TAVILY_API_KEY" not in env and env["EXTRA"] == "1"
    if WIN:
        assert env.get("SYSTEMROOT")  # node/python cannot start without it on Windows


def test_link_dir_falls_back_to_junction_on_windows(tmp_path, monkeypatch):
    src = tmp_path / "src nm"
    (src / "pkg").mkdir(parents=True)
    if not WIN:
        agent.link_dir(src, tmp_path / "dst")
        assert (tmp_path / "dst" / "pkg").is_dir()
        return

    def no_symlink(*a, **k):
        raise OSError(1314, "A required privilege is not held by the client")
    monkeypatch.setattr(agent.os, "symlink", no_symlink)
    agent.link_dir(src, tmp_path / "dst")
    assert (tmp_path / "dst" / "pkg").is_dir()
    import shutil
    shutil.rmtree(tmp_path / "dst")  # removing the sandbox must not delete the real dependency dir
    assert (src / "pkg").is_dir()


# --------------------------------------------------------------------------------------------- full task runs
SIGNUP = ROOT / "demos" / "ts_project"


def _signup(monkeypatch):
    import json
    t = {x["id"]: x for x in json.loads((ROOT / "demos" / "tasks" / "catalog.json").read_text())}["signup"]
    project = SIGNUP.resolve()
    tid = agent.create_task(project, t["prompt"], "vericode")
    return tid, agent.TaskRunner(tid, project, t["prompt"], "vericode", 1, live=False, acceptance=t.get("acceptance_tests")).run()


@pytest.mark.skipif(not (SIGNUP / "node_modules").is_dir(), reason="needs npm ci in demos/ts_project")
def test_missing_npm_after_coder_reports_structured_error(tmp_path, monkeypatch):
    """The original failure path: CODER writes code, then the test command cannot start."""
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(security, "network_isolation_available", lambda: False)
    monkeypatch.setattr(agent, "readiness_error", lambda *a: None)  # force the post-coder path
    tid, r = _signup(monkeypatch)
    assert r["outcome"] == "failed" and not r["success"]
    d = r["error_detail"]
    assert d["category"] == "executable_not_found" and d["stage"] == "tests" and "Node.js" in d["action"]
    assert len(r["attempts"]) == 1  # no repair tokens spent on a command that never ran
    assert "traceback" not in r
    assert Path(r["sandbox"]).is_dir()  # workspace copy kept until apply (no cleanup race)


@pytest.mark.skipif(not (SIGNUP / "node_modules").is_dir(), reason="needs npm ci in demos/ts_project")
def test_missing_npm_detected_before_any_llm_call(tmp_path, monkeypatch, client):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    tid, r = _signup(monkeypatch)
    assert r["error_detail"]["category"] == "executable_not_found" and r["error_detail"]["stage"] == "sandbox"
    assert r["tokens"]["total"] == 0
    body = client.get(f"/api/tasks/{tid}").json()  # propagated to the frontend
    res = body.get("result") or body
    assert res["error_detail"]["category"] == "executable_not_found"


def test_missing_node_modules_reported_not_installed(tmp_path, monkeypatch):
    import shutil
    proj = tmp_path / "my proj"
    shutil.copytree(SIGNUP, proj, ignore=shutil.ignore_patterns("node_modules"))
    tid = agent.create_task(proj, "x", "vericode")
    r = agent.TaskRunner(tid, proj, "x", "vericode", 1, live=False).run()
    assert r["error_detail"]["category"] == "dependencies_not_installed" and "npm ci" in r["error_detail"]["action"]
    assert r["tokens"]["total"] == 0 and not (proj / "node_modules").exists()  # never installs into the user's repo
