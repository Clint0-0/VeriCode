"""TypeScript verification against the REAL installed zod 3.23.8 in demos/ts_orders (Linux and Windows CI).

Reproduces the Windows pre-flight bug: check.cjs keyed its in-memory probe files by `path.join` (backslashes on
Windows) while TypeScript asks the host for normalised `D:/...` names -> probe never loaded ->
`TypeError: Cannot read properties of undefined (reading 'statements')` -> reported as NOT_FOUND."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from vericode import api_audit, jsinspect
from vericode.repo_intel import inspect_project
from vericode.skeleton import PlannedAPI, PlannedPackage
from vericode.verify_api import verify_planned_api

DEMO = Path(__file__).resolve().parents[2] / "demos" / "ts_orders"

pytestmark = pytest.mark.skipif(not (DEMO / "node_modules" / "zod").is_dir() or not jsinspect.ts_checker_available(),
                                reason="needs `npm ci` in demos/ts_orders and tools/ts-checker")


@pytest.fixture(scope="module")
def env():
    return inspect_project(DEMO.resolve())


def _verify(env, name, type_="function", args=None):
    pkg = PlannedPackage(package="zod", ecosystem="node", planned_apis=[PlannedAPI(import_path="zod", name=name, type=type_, arguments=args or [])])
    return verify_planned_api(env, pkg, pkg.planned_apis[0])


@pytest.mark.parametrize("name", ["z.object", "z.string", "z.number", "z.array", "object", "string"])
def test_valid_zod_builders_are_verified(env, name):
    f = _verify(env, name)
    assert f.status == "VERIFIED_LOCAL", (f.status, f.explanation, f.local.get("error"))
    assert f.installed_version == "3.23.8"


def test_schema_instance_method_safe_parse_is_verified(env):
    f = _verify(env, "ZodSchema.safeParse", "method", ["input"])  # ZodSchema = exported alias of ZodType
    assert f.status == "VERIFIED_LOCAL", (f.status, f.explanation, f.local.get("error"))
    assert f.local["kind"] in ("class", "type_alias", "alias", "interface") or f.local["signatures"]


def test_genuinely_missing_api_is_still_not_found(env):
    f = _verify(env, "z.objekt")
    assert f.status == "NOT_FOUND" and not f.local.get("error", "") .startswith("TypeError")
    g = _verify(env, "ZodSchema.safeParseStrict", "method")
    assert g.status == "NOT_FOUND", (g.status, g.explanation)


def test_type_error_in_planned_call_is_detected(env):
    """Diagnostics must survive the file-name comparison (was dropped on Windows: '\\' vs '/')."""
    f = _verify(env, "z.string", "function", ["12345"])
    assert f.status == "INCOMPATIBLE", (f.status, f.explanation)


def test_audit_finds_deprecated_zod_use_with_named_and_namespace_imports(tmp_path, env):
    proj = tmp_path / "proj copy"
    shutil.copytree(DEMO, proj, symlinks=True, ignore=shutil.ignore_patterns("node_modules"))
    (proj / "src" / "gen.ts").write_text(
        'import { z } from "zod";\nimport * as zod from "zod";\n'
        '// z.string().nonempty() in a comment is not code\n'
        'const s = "z.string().nonempty()";\n'
        'export const A = z.string().nonempty();\n'
        'export const B = zod.string()\n  .nonempty();\n')
    out = api_audit.audit_typescript(inspect_project(proj), [("src/gen.ts", None)], deps_root=str(DEMO.resolve()))
    dep = sorted((x["line"], x["status"]) for x in out if x["status"] == "DEPRECATED")
    assert dep == [(5, "DEPRECATED"), (7, "DEPRECATED")], out  # real calls only (multiline, alias), not comment/string
