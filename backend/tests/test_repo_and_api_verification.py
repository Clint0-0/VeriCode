import json

from vericode.repo_intel import (inspect_project, parse_package_lock, parse_pnpm_lock, parse_pyproject,
                                 parse_requirements, parse_toml_lock, parse_yarn_lock, select_relevant_files)
from vericode.skeleton import PlannedAPI, PlannedPackage
from vericode.verify_api import verify_planned_api


# ---------------------------------------------------------------- dependency tests
def test_declared_vs_installed_versions(fake_py_project):
    env = inspect_project(fake_py_project, use_cache=False)
    fl = env.dep("fakelib")
    assert fl.declared == ">=1.0" and fl.installed == "2.1.0" and fl.status == "ok"
    missing = env.dep("missinglib")
    assert missing.declared == "==3.0" and missing.installed is None and missing.status == "missing"
    assert ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"] in env.test_commands


def test_no_venv_never_reports_declared_as_installed(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests>=2\n")
    env = inspect_project(tmp_path, use_cache=False)
    d = env.dep("requests")
    assert d.installed is None and d.status == "not_installed_env_unavailable"
    assert any("NOT installed" in w for w in env.warnings)


def test_lockfile_parsers():
    assert parse_requirements("pydantic[email]>=2,<3 ; python_version>'3'\n# c\n-e .\n") == {"pydantic": ">=2,<3"}
    assert parse_pyproject('[project]\ndependencies=["fastapi==0.110"]\n[tool.poetry.dependencies]\npython="^3.11"\nhttpx="^0.27"\n') == {"fastapi": "==0.110", "httpx": "^0.27"}
    assert parse_toml_lock('[[package]]\nname="httpx"\nversion="0.27.0"\n') == {"httpx": "0.27.0"}
    assert parse_package_lock(json.dumps({"packages": {"": {}, "node_modules/zod": {"version": "3.23.8"}, "node_modules/a/node_modules/zod": {"version": "1.0.0"}}})) == {"zod": "3.23.8"}
    assert parse_yarn_lock('"react@^18.2.0":\n  version "18.3.1"\n') == {"react": "18.3.1"}
    assert parse_pnpm_lock("packages:\n  /react@18.3.1:\n    resolution: {}\n")["react"] == "18.3.1"


def test_lockfile_change_invalidates_cache(fake_py_project):
    e1 = inspect_project(fake_py_project)
    (fake_py_project / "requirements.txt").write_text("fakelib>=2.0\n")
    e2 = inspect_project(fake_py_project)
    assert e1.fingerprint != e2.fingerprint
    assert e2.dep("fakelib").declared == ">=2.0" and e2.dep("missinglib") is None


def test_relevant_file_selection_explains_reasons(sample_project):
    env = inspect_project(sample_project)
    sel = select_relevant_files(env, "Add a priority_summary() method to TaskStore")
    assert sel[0]["path"] == "taskboard/storage.py"
    assert sel[0]["reasons"]
    assert all("billing" not in s["path"] for s in sel)


# ---------------------------------------------------------------- API verification tests
def _check(env, name, typ="function", args=None, assumed=None, import_path="fakelib"):
    pkg = PlannedPackage(package="fakelib", ecosystem="python", assumed_version=assumed,
                         planned_apis=[PlannedAPI(import_path=import_path, name=name, type=typ, arguments=args or [])])
    return verify_planned_api(env, pkg, pkg.planned_apis[0])


def test_valid_api(fake_py_project):
    env = inspect_project(fake_py_project, use_cache=False)
    f = _check(env, "connect", args=["timeout"])
    assert f.status == "VERIFIED_LOCAL" and f.verification_confidence == "high" and f.risk_score == 0


def test_star_reexport_and_inherited_method(fake_py_project):
    env = inspect_project(fake_py_project, use_cache=False)
    assert _check(env, "helper", args=["y"]).status == "VERIFIED_LOCAL"
    assert _check(env, "Client.close", typ="method").status == "VERIFIED_LOCAL"


def test_missing_import(fake_py_project):
    env = inspect_project(fake_py_project, use_cache=False)
    f = _check(env, "Session", typ="class")
    assert f.status == "NOT_FOUND" and f.risk_score >= 60


def test_nonexistent_method(fake_py_project):
    env = inspect_project(fake_py_project, use_cache=False)
    assert _check(env, "Client.stream", typ="method").status == "NOT_FOUND"


def test_unsupported_and_rejected_arguments(fake_py_project):
    env = inspect_project(fake_py_project, use_cache=False)
    f = _check(env, "connect", args=["retries"])
    assert f.status == "INCOMPATIBLE" and f.argument_checks[0]["status"] == "unsupported"
    g = _check(env, "Client", typ="class", args=["url", "retries"])
    assert g.status == "INCOMPATIBLE" and "max_retries" in g.suggested_correction
    h = _check(env, "Client", typ="class", args=["verify_ssl"])
    assert h.status == "VERIFIED_LOCAL" and h.verification_confidence == "medium"  # swallowed by **kwargs: uncertain


def test_deprecated_api(fake_py_project):
    env = inspect_project(fake_py_project, use_cache=False)
    f = _check(env, "Client.fetch", typ="method")
    assert f.status == "DEPRECATED" and "send" in f.suggested_correction
    assert _check(env, "old_connect", import_path="fakelib.core").status == "DEPRECATED"


def test_version_assumption_mismatch_is_stale(fake_py_project):
    env = inspect_project(fake_py_project, use_cache=False)
    f = _check(env, "connect", assumed="1.4")
    assert f.status == "STALE" and any(r["factor"] == "assumed_major_mismatch" for r in f.risk_factors)


def test_uncertain_when_env_missing(tmp_path):
    (tmp_path / "requirements.txt").write_text("fakelib>=1\n")
    env = inspect_project(tmp_path, use_cache=False)
    f = _check(env, "connect")
    assert f.status == "NOT_FOUND" and "not installed" in f.explanation


def test_real_pydantic_incompatibilities(sample_project):
    env = inspect_project(sample_project)
    pkg = PlannedPackage(package="pydantic", ecosystem="python", assumed_version="1.10", planned_apis=[
        PlannedAPI(import_path="pydantic", name="Field", type="function", arguments=["regex"]),
        PlannedAPI(import_path="pydantic", name="validator", type="decorator"),
        PlannedAPI(import_path="pydantic", name="BaseModel.dict", type="method"),
        PlannedAPI(import_path="pydantic", name="BaseSettings", type="class"),
        PlannedAPI(import_path="pydantic", name="field_validator", type="decorator", arguments=["mode"]),
    ])
    st = {a.name: verify_planned_api(env, pkg, a) for a in pkg.planned_apis}
    assert st["Field"].status == "INCOMPATIBLE" and "pattern" in st["Field"].suggested_correction
    assert st["validator"].status == "DEPRECATED" and "field_validator" in st["validator"].suggested_correction
    assert st["BaseModel.dict"].status == "DEPRECATED" and "model_dump" in st["BaseModel.dict"].suggested_correction
    assert st["BaseSettings"].status == "NOT_FOUND" and "pydantic-settings" in st["BaseSettings"].suggested_correction
    assert st["field_validator"].status == "STALE"  # exists; planner assumed v1


def test_js_export_verification(tmp_path):
    from vericode import jsinspect
    nm = tmp_path / "node_modules" / "mini"
    (nm / "dist").mkdir(parents=True)
    (nm / "package.json").write_text(json.dumps({"name": "mini", "version": "4.0.1", "exports": {".": {"types": "./dist/index.d.ts", "import": "./dist/index.js"}}}))
    (nm / "dist" / "index.d.ts").write_text("export * from './core';\nexport { parse as parseIt } from './parse';\n")
    (nm / "dist" / "core.d.ts").write_text("/** @deprecated use createClient */\nexport declare function makeClient(url: string, opts?: object): void;\nexport declare function createClient(url: string, opts?: object): void;\nexport declare class Store { get(key: string): string; }\n")
    (nm / "dist" / "parse.d.ts").write_text("export declare function parse(s: string): number;\n")
    r = jsinspect.resolve(tmp_path / "node_modules", "mini", "createClient")
    assert r.found and r.package_version == "4.0.1" and [p["name"] for p in r.params] == ["url", "opts"]
    assert jsinspect.resolve(tmp_path / "node_modules", "mini", "makeClient").deprecated
    assert jsinspect.resolve(tmp_path / "node_modules", "mini", "parseIt").found
    assert jsinspect.resolve(tmp_path / "node_modules", "mini", "Store.get").found
    assert not jsinspect.resolve(tmp_path / "node_modules", "mini", "Store.put").found
    assert not jsinspect.resolve(tmp_path / "node_modules", "mini", "nope").found
    assert not jsinspect.resolve(tmp_path / "node_modules", "absent", "x").found
