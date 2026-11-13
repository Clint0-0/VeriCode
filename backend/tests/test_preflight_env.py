"""Python environment discovery, dependency statuses, pydantic v2 migrations and verification counts."""
from __future__ import annotations

import os
import shutil
import sys
import venv
from pathlib import Path

import pytest

from conftest import ROOT
from vericode import agent, pyenv, verify_api
from vericode.api_audit import audit_python
from vericode.repo_intel import inspect_project
from vericode.skeleton import PlannedAPI, PlannedPackage

LEDGER = ROOT / "demos" / "py_ledger"
HAVE_LEDGER_VENV = (LEDGER / ".venv").is_dir()


def make_venv(d: Path) -> Path:
    venv.create(d, with_pip=False, symlinks=os.name != "nt")
    return d


def fake_env_dir(d: Path, windows: bool = False, runnable: bool = False) -> Path:
    """Environment layout without a working interpreter (or with a real one when runnable=True)."""
    if runnable:
        return make_venv(d)
    sp = d / ("Lib" if windows else "lib/python3.13") / "site-packages"
    sp.mkdir(parents=True)
    (d / "pyvenv.cfg").write_text("home = /nowhere\n")
    exe = d / ("Scripts/python.exe" if windows else "bin/python")
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_text("not a program\n")
    exe.chmod(0o755)
    return d


def add_dist(sp: Path, name: str, version: str, module: str | None = None, body: str = "") -> None:
    (sp / f"{name.replace('-', '_')}-{version}.dist-info").mkdir(parents=True)
    (sp / f"{name.replace('-', '_')}-{version}.dist-info" / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n")
    if module:
        (sp / module).mkdir(parents=True, exist_ok=True)
        (sp / module / "__init__.py").write_text(body)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("VIRTUAL_ENV", "POETRY_VIRTUALENVS_PATH", "POETRY_CACHE_DIR", "WORKON_HOME", "CONDA_ENVS_PATH", "CONDA_PREFIX"):
        monkeypatch.delenv(k, raising=False)
    pyenv._PROBE_CACHE.clear()


# ------------------------------------------------------------------------------------------ discovery
def test_windows_layout_detected_statically(tmp_path):
    fake_env_dir(tmp_path / ".venv", windows=True)
    c = pyenv.find_candidates(tmp_path)[0]
    assert c["source"] == "in-project (.venv)" and c["interpreter"].endswith(os.path.join("Scripts", "python.exe"))
    assert c["site_packages"].endswith(os.path.join("Lib", "site-packages"))


def test_posix_or_native_venv_available(tmp_path):
    make_venv(tmp_path / ".venv")
    e = pyenv.discover(tmp_path)
    assert e.status == "AVAILABLE" and e.source == "in-project (.venv)" and e.version == sys.version.split()[0]
    assert Path(e.site_packages).is_dir()


@pytest.mark.parametrize("name", ["venv", "env"])
def test_venv_and_env_dirs(tmp_path, name):
    make_venv(tmp_path / name)
    assert pyenv.discover(tmp_path).source == f"in-project ({name})"


def test_plain_env_code_folder_is_not_an_environment(tmp_path):
    (tmp_path / "env").mkdir()
    (tmp_path / "env" / "settings.py").write_text("X = 1\n")
    assert pyenv.discover(tmp_path).status == "UNAVAILABLE"


def test_virtual_env_only_inside_workspace(tmp_path, monkeypatch):
    inside = make_venv(tmp_path / "proj" / "custom-env")
    monkeypatch.setenv("VIRTUAL_ENV", str(inside))
    assert pyenv.discover(tmp_path / "proj").source == "VIRTUAL_ENV"
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)  # e.g. VeriCode's own venv: never used for a workspace
    assert pyenv.discover(tmp_path / "other").status == "UNAVAILABLE"


def test_poetry_env_found_by_its_hash(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text('[tool.poetry]\nname = "Ledger App"\n')
    (proj / "poetry.lock").write_text('[[package]]\nname = "pydantic"\nversion = "2.9.2"\n')
    store = tmp_path / "poetry-envs"
    monkeypatch.setenv("POETRY_VIRTUALENVS_PATH", str(store))
    fake_env_dir(store / f"{pyenv.poetry_env_prefix(proj.resolve())}-py3.13")
    fake_env_dir(store / "someone-else-AbCdEfGh-py3.13")  # another project's env: ignored
    c = pyenv.find_candidates(proj)
    assert [x["source"] for x in c] == ["poetry"] and pyenv.poetry_env_prefix(proj.resolve()).startswith("ledger_app-")


def test_pipenv_env_found_by_its_hash(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "Pipfile").write_text('[packages]\npydantic = "==2.9.2"\n')
    monkeypatch.setenv("WORKON_HOME", str(tmp_path / "venvs"))
    fake_env_dir(tmp_path / "venvs" / pyenv.pipenv_env_name(proj.resolve()))
    assert [x["source"] for x in pyenv.find_candidates(proj)] == ["pipenv"]


def test_uv_project_uses_in_project_venv_and_uv_lock(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\ndependencies=["pydantic>=2"]\n')
    (tmp_path / "uv.lock").write_text('[[package]]\nname = "pydantic"\nversion = "2.9.2"\n')
    make_venv(tmp_path / ".venv")
    env = inspect_project(tmp_path, use_cache=False)
    d = env.dep("pydantic")
    assert env.environments["python"]["status"] == "AVAILABLE"
    assert (d.declared, d.resolved, d.installed, d.status) == (">=2", "2.9.2", None, "NOT_INSTALLED")


def test_conda_env_from_environment_yml(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "environment.yml").write_text("name: ledger-env\ndependencies:\n  - python=3.12\n  - pydantic=2.9.2\n")
    envs = tmp_path / "conda" / "envs"
    d = fake_env_dir(envs / "ledger-env")
    (d / "conda-meta").mkdir()
    monkeypatch.setenv("CONDA_ENVS_PATH", str(envs))
    c = pyenv.find_candidates(proj)
    assert c[0]["source"] == "conda (ledger-env)"
    assert inspect_project(proj, use_cache=False).dep("pydantic").declared == "==2.9.2"


def test_no_environment(tmp_path):
    e = pyenv.discover(tmp_path)
    assert e.status == "UNAVAILABLE" and "No Python environment" in e.detail


def test_multiple_environments_ambiguous_uses_highest_priority(tmp_path):
    make_venv(tmp_path / ".venv")
    make_venv(tmp_path / "venv")
    e = pyenv.discover(tmp_path)
    assert e.status == "AMBIGUOUS" and e.source == "in-project (.venv)" and len(e.candidates) == 2


def test_invalid_configured_interpreter(tmp_path):
    e = pyenv.discover(tmp_path, configured=str(tmp_path / "nope" / "python"))
    assert e.status == "CONFIGURATION_ERROR" and "not usable" in e.detail
    with pytest.raises(ValueError):
        pyenv.set_configured_interpreter(tmp_path, "relative/python")
    with pytest.raises(ValueError):
        pyenv.set_configured_interpreter(tmp_path, str(tmp_path / "missing" / "python"))


def test_interpreter_that_cannot_launch(tmp_path):
    fake_env_dir(tmp_path / ".venv", windows=os.name == "nt")
    e = pyenv.discover(tmp_path)
    assert e.status == "CONFIGURATION_ERROR" and "not usable" in e.detail


def test_configured_interpreter_via_api(client, tmp_path, monkeypatch):
    from vericode.config import settings
    ws = tmp_path / "ws"
    proj = ws / "proj"
    proj.mkdir(parents=True)
    (proj / "requirements.txt").write_text("pydantic==2.9.2\n")
    other = make_venv(tmp_path / "elsewhere")
    monkeypatch.setattr(settings, "workspaces_root", str(ws))
    py = pyenv.interpreter_in(other)
    r = client.post("/api/projects/python-interpreter", json={"path": "proj", "interpreter": str(py)})
    assert r.status_code == 200 and r.json()["environments"]["python"]["source"] == "configured"
    assert client.post("/api/projects/python-interpreter", json={"path": "proj", "interpreter": "python"}).status_code == 400
    r = client.post("/api/projects/python-interpreter", json={"path": "proj", "interpreter": ""})
    assert r.json()["environments"]["python"]["status"] == "UNAVAILABLE"


# ------------------------------------------------------------------------------------------ dependency statuses
def _proj(tmp_path, reqs: str, env: bool, lock: str | None = None, installed: dict | None = None) -> Path:
    (tmp_path / "requirements.txt").write_text(reqs)
    if lock:
        (tmp_path / "poetry.lock").write_text(lock)
    if env:
        d = fake_env_dir(tmp_path / ".venv")
        os.remove(pyenv.interpreter_in(d))  # metadata-only environment: no interpreter needed
        for n, v in (installed or {}).items():
            add_dist(pyenv.static_site_packages(d), n, v)
    return tmp_path


def test_dependency_statuses(tmp_path):
    p = _proj(tmp_path, "a==1.0\nb>=2\nc==3.0\nd==1\n", env=True,
              lock='[[package]]\nname="a"\nversion="1.0"\n[[package]]\nname="c"\nversion="3.1"\n', installed={"a": "1.0", "b": "1.5", "c": "3.0"})
    env = inspect_project(p, use_cache=False)
    st = {d.name: (d.declared, d.resolved, d.installed, d.status) for d in env.dependencies}
    assert st["a"] == ("==1.0", "1.0", "1.0", "INSTALLED")
    assert st["b"] == (">=2", None, "1.5", "VERSION_MISMATCH")  # violates declared range
    assert st["c"] == ("==3.0", "3.1", "3.0", "VERSION_MISMATCH")  # differs from lockfile
    assert st["d"] == ("==1", None, None, "NOT_INSTALLED")  # environment available, package absent
    assert env.environments["python"]["status"] == "AVAILABLE"


def test_environment_unavailable_is_unknown_not_missing(tmp_path):
    p = _proj(tmp_path, "pydantic==2.9.2\nzzz==1\n", env=False, lock='[[package]]\nname="pydantic"\nversion="2.9.2"\n')
    env = inspect_project(p, use_cache=False)
    assert env.dep("pydantic").status == "UNKNOWN" and env.dep("pydantic").resolved == "2.9.2"
    assert env.dep("zzz").status == "UNRESOLVED"  # lockfile exists but does not list it; installed unknown
    pkg = PlannedPackage(package="pydantic", ecosystem="python", planned_apis=[PlannedAPI(import_path="pydantic", name="BaseModel", type="class")])
    f = verify_api.verify_planned_api(env, pkg, pkg.planned_apis[0])
    assert f.status == "UNCERTAIN" and f.verdict == "UNCERTAIN" and f.environment_status == "UNAVAILABLE"


# ------------------------------------------------------------------------------------------ pydantic v2
def _verify(env, package, import_path, name, type_="class"):
    pkg = PlannedPackage(package=package, ecosystem="python", planned_apis=[PlannedAPI(import_path=import_path, name=name, type=type_)])
    return verify_api.verify_planned_api(env, pkg, pkg.planned_apis[0])


@pytest.mark.skipif(not HAVE_LEDGER_VENV, reason="needs demos/py_ledger/.venv (scripts/setup_benchmark_repos.sh)")
def test_pydantic_v2_base_settings_moved_and_companion_missing():
    env = inspect_project(LEDGER.resolve())
    f = _verify(env, "pydantic", "pydantic", "BaseSettings")
    assert f.status == "NOT_FOUND" and "pydantic-settings" in f.explanation
    assert "from pydantic_settings import BaseSettings" in f.suggested_correction and "NOT declared or installed" in f.suggested_correction
    g = _verify(env, "pydantic-settings", "pydantic_settings", "BaseSettings")
    assert g.status == "NOT_FOUND" and "not declared or installed" in g.explanation  # never assumed to exist
    assert _verify(env, "pydantic", "pydantic", "BaseModel.model_dump", "method").status == "VERIFIED_LOCAL"
    assert _verify(env, "pydantic", "pydantic", "BaseModel.dict", "method").status == "DEPRECATED"
    assert _verify(env, "pydantic", "pydantic", "DoesNotExist").status == "NOT_FOUND"


def test_companion_package_installed_is_verified(tmp_path):
    p = _proj(tmp_path, "pydantic==2.9.2\npydantic-settings==2.5.2\n", env=True)
    add_dist(pyenv.static_site_packages(p / ".venv"), "pydantic-settings", "2.5.2", "pydantic_settings", "class BaseSettings:\n    pass\n")
    env = inspect_project(p, use_cache=False)
    f = verify_api.APIFinding(package="pydantic", ecosystem="python", planned_api="pydantic.BaseSettings", api_type="class",
                              arguments=[], installed_version="2.9.2", assumed_version=None)
    verify_api._companion_package(env, PlannedAPI(import_path="pydantic", name="BaseSettings", type="class"), f,
                                  "`BaseSettings` has been moved to the `pydantic-settings` package.")
    assert f.suggested_correction.startswith("from pydantic_settings import BaseSettings") and "verified in installed pydantic-settings 2.5.2" in f.suggested_correction


def test_companion_package_declared_not_installed(tmp_path):
    p = _proj(tmp_path, "pydantic==2.9.2\npydantic-settings==2.5.2\n", env=True)
    env = inspect_project(p, use_cache=False)
    f = verify_api.APIFinding(package="pydantic", ecosystem="python", planned_api="pydantic.BaseSettings", api_type="class",
                              arguments=[], installed_version="2.9.2", assumed_version=None)
    verify_api._companion_package(env, PlannedAPI(import_path="pydantic", name="BaseSettings", type="class"), f,
                                  "`BaseSettings` has been moved to the `pydantic-settings` package.")
    assert "declared (==2.5.2) but not installed" in f.suggested_correction


@pytest.mark.skipif(not HAVE_LEDGER_VENV, reason="needs demos/py_ledger/.venv")
def test_audit_aliased_imports():
    env = inspect_project(LEDGER.resolve())
    code = "import pydantic as pd\nfrom pydantic import BaseSettings as BS\nclass T(BS):\n    pass\nm = pd.BaseModel()\n"
    got = {(f["line"], f["planned_api"], f["status"]) for f in audit_python(env, "x.py", code, None)}
    assert (3, "pydantic.BaseSettings", "NOT_FOUND") in got  # was missed: alias + bare-name base class
    assert (5, "pydantic.BaseModel", "VERIFIED_LOCAL") in got


@pytest.mark.skipif(not HAVE_LEDGER_VENV, reason="needs demos/py_ledger/.venv")
def test_py_ledger_environment_reported(tmp_path):
    env = inspect_project(LEDGER.resolve())
    pe = env.environments["python"]
    assert pe["status"] in ("AVAILABLE", "AMBIGUOUS") and pe["interpreter"]
    assert {d.name: d.status for d in env.dependencies} == {"pydantic": "INSTALLED", "pytest": "INSTALLED"}
    copy = tmp_path / "py_ledger"  # same project without its environment
    shutil.copytree(LEDGER, copy, ignore=shutil.ignore_patterns(".venv"))
    e2 = inspect_project(copy, use_cache=False)
    assert e2.environments["python"]["status"] == "UNAVAILABLE"
    assert {d.name: d.status for d in e2.dependencies} == {"pydantic": "UNKNOWN", "pytest": "UNKNOWN"}


# ------------------------------------------------------------------------------------------ counts and run ids
def test_summary_distinguishes_planned_analyzed_verified():
    fs = [{"status": s} for s in ("VERIFIED_LOCAL", "DEPRECATED", "NOT_FOUND", "UNCERTAIN", "ERROR", "INCOMPATIBLE")]
    s = verify_api.summarize(fs)
    assert (s["planned"], s["analyzed"], s["verified"], s["not_found"], s["uncertain"], s["error"], s["problems"]) == (6, 6, 3, 1, 1, 1, 3)
    assert verify_api.summary_text(s).startswith("Analyzed 6 of 6 planned APIs: 3 verified, 1 not found")


def test_project_cmd_uses_discovered_interpreter():
    env = type("E", (), {"environments": {"python": {"status": "AVAILABLE", "interpreter": "/x/venv/bin/python", "source": "in-project (venv)"}}})()
    assert agent.project_cmd(["python", "-m", "pytest"], env, "process") == ["/x/venv/bin/python", "-m", "pytest"]
    assert agent.project_cmd(["python", "-m", "pytest"], env, "docker") == ["python", "-m", "pytest"]
    env.environments["python"]["source"] = "in-project (.venv)"  # the sandbox already provides .venv
    assert agent.project_cmd(["python", "-m", "pytest"], env, "process") == ["python", "-m", "pytest"]


def test_mock_run_counts_agree_and_belong_to_the_run(sample_project, client):
    """Run log, stored pre-flight report and API response use one summary; every finding carries its run id."""
    import json
    t = {x["id"]: x for x in json.loads((ROOT / "demos" / "tasks" / "catalog.json").read_text())}["users"]
    tid = agent.create_task(sample_project.resolve(), t["prompt"], "vericode_full")
    r = agent.TaskRunner(tid, sample_project.resolve(), t["prompt"], "vericode_full", 3, live=False,
                         acceptance=t.get("acceptance_tests")).run()
    body = client.get(f"/api/tasks/{tid}").json()
    pf = body["preflight"]
    ev = next(e for e in body["events"] if e["stage"] == "verify")
    assert ev["data"]["summary"] == pf["summary"] == verify_api.summarize(pf["findings"])
    assert ev["message"] == verify_api.summary_text(pf["summary"]) and not ev["message"].startswith("Verified ")
    assert pf["task_id"] == tid and all(f["task_id"] == tid for f in pf["findings"])
    assert r["outcome"] == "succeeded" and r["diff"]  # successful coding task keeps its diff
