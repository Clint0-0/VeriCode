"""Classification and robustness of TypeScript API verification (checker failures are ERROR, never NOT_FOUND)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from vericode import agent, api_audit, jsinspect, verify_api
from vericode.repo_intel import inspect_project
from vericode.skeleton import PlannedAPI, PlannedPackage
from vericode.tavily import SearchOutcome, TavilyResult as SearchResult

DEMO = Path(__file__).resolve().parents[2] / "demos" / "ts_orders"
HAVE_TS = (DEMO / "node_modules" / "zod").is_dir() and jsinspect.ts_checker_available()


@pytest.fixture
def env():
    return inspect_project(DEMO.resolve())


def _verify(env, name="z.object", type_="function"):
    pkg = PlannedPackage(package="zod", ecosystem="node", planned_apis=[PlannedAPI(import_path="zod", name=name, type=type_)])
    return verify_api.verify_planned_api(env, pkg, pkg.planned_apis[0])


CRASH = {"available": True, "internal_error": True,
         "error": "TypeError: Cannot read properties of undefined (reading 'statements')\n    at main (check.cjs:101:18)"}


@pytest.mark.parametrize("result", [
    CRASH,
    {"available": True, "internal_error": True, "error": "TypeScript check timed out after 45s"},
    {"available": True, "internal_error": True, "error": "TypeScript checker produced no output (exit 1): boom"},
])
def test_checker_failure_is_error_not_not_found(env, monkeypatch, result):
    monkeypatch.setattr(jsinspect, "ts_compiler_check", lambda *a, **k: dict(result))
    f = _verify(env)
    assert f.status == "ERROR" and f.status != "NOT_FOUND"
    assert "NOT checked" in f.explanation and "verification_error" in [r["factor"] for r in f.risk_factors]


def test_documentation_hit_does_not_turn_error_into_verified(env, monkeypatch):
    monkeypatch.setattr(jsinspect, "ts_compiler_check", lambda *a, **k: dict(CRASH))
    f = _verify(env)

    class Docs:
        def search(self, q, include_domains=None, max_results=4):
            return SearchOutcome(ok=True, status="ok", results=[SearchResult(title="zod", url="https://zod.dev/api", content="z.object() ...")])
    monkeypatch.setattr(verify_api, "_doc_domains", lambda p: ["zod.dev"])
    verify_api.live_verify(f, env, Docs())
    assert f.status == "ERROR" and f.live["sources"][0]["mentions_api"]  # evidence kept separately, verdict unchanged


@pytest.mark.skipif(not jsinspect.ts_checker_available(), reason="needs tools/ts-checker")
def test_real_subprocess_failure_is_classified(env, monkeypatch, tmp_path):
    bad = tmp_path / "check.cjs"
    bad.write_text("process.exit(3)\n")
    monkeypatch.setattr(jsinspect, "CHECKER", bad)
    monkeypatch.setattr(jsinspect, "ts_checker_available", lambda: True)
    r = jsinspect.ts_compiler_check(DEMO, "zod", "z", "object")
    assert r["internal_error"] and "exit 3" in r["error"]


# ------------------------------------------------------------------------------------------ audit robustness
def test_audit_crash_is_error_not_clean(env, monkeypatch, tmp_path):
    (tmp_path / "node_modules" / "typescript").mkdir(parents=True)
    bad = tmp_path / "audit.cjs"
    bad.write_text("process.stdout.write(JSON.stringify({findings: [], internal_error: true, error: 'TypeError: x'}))\n")
    monkeypatch.setattr(api_audit, "AUDITOR", bad)
    out = api_audit.audit_typescript(env, [("src/validation.ts", None)])
    assert [x["status"] for x in out] == ["ERROR"] and "NOT checked" in out[0]["explanation"]


@pytest.mark.skipif(not HAVE_TS, reason="needs npm ci in demos/ts_orders and tools/ts-checker")
def test_audit_edge_files_empty_malformed_missing_js(tmp_path):
    proj = tmp_path / "p q"
    shutil.copytree(DEMO, proj, symlinks=True, ignore=shutil.ignore_patterns("node_modules"))
    (proj / "src" / "empty.ts").write_text("")
    (proj / "src" / "broken.ts").write_text("export const = ;\nimport { z } from 'zod'\nexport const A = z.string().nonempty(\n")
    (proj / "src" / "gen.js").write_text("import { z } from 'zod'\nexport const A = z.string().nonempty()\n")
    files = [("src/empty.ts", None), ("src/broken.ts", None), ("src/missing.ts", None), ("src/gen.js", None)]
    out = api_audit.audit_typescript(inspect_project(proj), files, deps_root=str(DEMO.resolve()))
    by = {(x.get("file"), x["status"]) for x in out}
    assert ("src/missing.ts", "ERROR") in by  # not loadable -> reported as not checked, not silently skipped
    assert ("src/gen.js", "DEPRECATED") in by  # JavaScript audited
    assert ("src/broken.ts", "DEPRECATED") in by  # malformed file still parsed (error-tolerant), no crash
    assert not any(x.get("file") == "src/empty.ts" for x in out)


def test_audit_changes_counts_errors_separately(env, monkeypatch, tmp_path):
    (tmp_path / "a.ts").write_text("x\n")
    monkeypatch.setattr(api_audit, "audit_typescript", lambda *a, **k: [{"planned_api": "(typescript audit)", "status": "ERROR", "explanation": "x"}])
    r = api_audit.audit_changes(env, tmp_path, ["a.ts"], {"a.ts": None})
    assert r["checked"] == 0 and len(r["errors"]) == 1 and not r["problems"] and "audit ERROR" in r["summary"]


# ------------------------------------------------------------------------------------------ still_used scan
def _diff(code: str) -> str:
    return "+++ b/src/x.ts\n" + "".join(f"+{l}\n" for l in code.splitlines())


def test_still_used_ignores_comments_and_strings():
    f = [{"planned_api": "zod:objekt", "status": "NOT_FOUND", "ecosystem": "node"}]
    clean = _diff('import { z } from "zod"\n// z.objekt({}) was wrong\nconst msg = "objekt(" + `objekt(`\n/* objekt( */\nexport const S = z.object({})')
    assert agent.api_corrections(f, clean)[0]["result"] == "corrected"
    used = _diff('import { z } from "zod"\nexport const S = z\n  .objekt({})')
    assert agent.api_corrections(f, used)[0]["result"] == "still_used"


def test_still_used_python_comments_and_docstrings():
    f = [{"planned_api": "pydantic.BaseModel.dict", "status": "DEPRECATED", "ecosystem": "python"}]
    assert agent.api_corrections(f, _diff('x = m.model_dump()  # not m.dict()\n"""m.dict() is gone"""'))[0]["result"] == "corrected"
    assert agent.api_corrections(f, _diff("x = m.dict()"))[0]["result"] == "still_used"


def test_errors_and_verified_are_not_correction_targets():
    fs = [{"planned_api": "zod:object", "status": "VERIFIED_LOCAL"}, {"planned_api": "zod:string", "status": "ERROR"}]
    assert agent.api_corrections(fs, _diff("z.object({}); z.string()")) == []


def test_ts_private_fields_survive_stripping():
    assert "#count" in agent.strip_comments_and_strings("class A { #count = 0 }", "node")


def test_correction_is_confirmed_by_final_audit():
    f = [{"planned_api": "zod:ZodString.nonempty", "status": "DEPRECATED", "ecosystem": "node"}]
    d = _diff("export const A = z.string().min(1)")
    ok = agent.api_corrections(f, d, {"problems": [], "errors": []})[0]
    assert ok["result"] == "corrected" and ok["verified"] is True
    # text looks clean, but the compiler audit of the changed source still sees the deprecated call (e.g. via alias)
    bad = agent.api_corrections(f, d, {"problems": [{"planned_api": "zod:ZodString.nonempty"}], "errors": []})[0]
    assert bad["result"] == "still_used"
    unk = agent.api_corrections(f, d, {"problems": [], "errors": [{"status": "ERROR"}]})[0]
    assert unk["result"] == "corrected" and unk["verified"] is False and "NOT verified" in unk["detail"]
