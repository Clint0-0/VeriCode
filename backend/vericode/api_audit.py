"""Post-generation API audit: verify the third-party APIs the generated code ACTUALLY uses, with no LLM call.

The pre-flight planner predicts which APIs a change will use; this audit reads the code the coder wrote instead.
Only lines added by the change are audited, so pre-existing code is never blamed.

Python: the changed files are parsed with `ast`. Imports from installed/declared third-party packages are
resolved to (module, qualified name) pairs, including attribute chains (`pkg.sub.fn`), decorators, keyword
arguments, and methods called on subclasses or instances of third-party classes (`self.dict()` in a
`BaseModel` subclass -> `pydantic.BaseModel.dict`). Each usage is checked by the same resolver as the
pre-flight (installed source; isolated runtime introspection only as a fallback).

TypeScript/JavaScript: tools/ts-checker/audit.cjs runs the TypeScript compiler over the changed files with
the project's own node_modules and reports, on added lines only, uses of @deprecated third-party symbols or
overloads and compiler errors attributable to a third-party symbol (missing export, missing member, wrong
call). Nothing is executed.
"""
from __future__ import annotations

import ast
import difflib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .repo_intel import ProjectEnvironment, norm_pkg
from .skeleton import PlannedAPI, PlannedPackage

PROBLEM = {"NOT_FOUND", "INCOMPATIBLE", "DEPRECATED"}
AUDITOR = Path(__file__).resolve().parents[2] / "tools" / "ts-checker" / "audit.cjs"
_STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def added_lines(before: str | None, after: str) -> set[int] | None:
    """1-based line numbers of `after` that are new or changed. None means the whole file is new."""
    if before is None:
        return None
    sm = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines(), autojunk=False)
    out: set[int] = set()
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "insert"):
            out.update(range(j1 + 1, j2 + 1))
    return out


def _dotted(node: ast.AST) -> list[str] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return parts[::-1]
    return None


def _call_args(call: ast.Call) -> list[str]:
    args = []
    for a in call.args:
        args.append("*" if isinstance(a, ast.Starred) else "<value>")
    for k in call.keywords:
        args.append(f"{k.arg}=<value>" if k.arg else "**")
    return args


class _PyUsage(ast.NodeVisitor):
    """Collect (module, qualname, type, args, line) for third-party symbols."""

    def __init__(self, resolve_module):
        self.resolve_module = resolve_module  # top-level module -> dependency name or None
        self.alias: dict[str, tuple[str, str]] = {}  # local name -> (module, qualname or "")
        self.subclass: dict[str, tuple[str, str]] = {}  # local class name -> third-party base (module, qualname)
        self.class_methods: dict[str, set[str]] = {}
        self.instances: dict[str, tuple[str, str]] = {}  # variable -> third-party class (module, qualname)
        self.usages: list[dict] = []
        self._class: list[str] = []
        self._callees: set[int] = set()  # attribute nodes already audited as the callee of a call

    # imports
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level or not node.module or not self.resolve_module(node.module.split(".")[0]):
            return
        for a in node.names:
            if a.name != "*":
                self.alias[a.asname or a.name] = (node.module, a.name)
                self._use(node.module, a.name, "attribute", [], node.lineno, kind="import")

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            if self.resolve_module(a.name.split(".")[0]):
                self.alias[a.asname or a.name.split(".")[0]] = (a.name if a.asname else a.name.split(".")[0], "")
                self._use(a.name, "", "module", [], node.lineno, kind="import")

    def _resolve(self, parts: list[str]) -> tuple[str, str] | None:
        head = self.alias.get(parts[0])
        if head:
            mod, qual = head
            rest = ".".join(parts[1:])
            return mod, ".".join(p for p in (qual, rest) if p)
        if parts[0] in self.instances and len(parts) > 1:
            mod, qual = self.instances[parts[0]]
            return mod, f"{qual}.{'.'.join(parts[1:])}"
        if parts[0] in ("self", "cls") and self._class and len(parts) == 2:
            base = self.subclass.get(self._class[-1])
            if base and parts[1] not in self.class_methods.get(self._class[-1], set()):
                return base[0], f"{base[1]}.{parts[1]}"
        if parts[0] in self.subclass and len(parts) == 2 and parts[1] not in self.class_methods.get(parts[0], set()):
            mod, qual = self.subclass[parts[0]]
            return mod, f"{qual}.{parts[1]}"
        return None

    def _use(self, module: str, qual: str, typ: str, args: list[str], line: int, kind: str = "use") -> None:
        self.usages.append({"module": module, "name": qual, "type": typ, "args": args, "line": line, "kind": kind})

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_methods[node.name] = {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for b in node.bases:
            parts = _dotted(b)
            r = self._resolve(parts) if parts else None
            if r:
                self.subclass[node.name] = r
        self._class.append(node.name)
        self.generic_visit(node)
        self._class.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call):
            parts = _dotted(node.value.func)
            r = self._resolve(parts) if parts else None
            if not r and parts and parts[0] in self.subclass and len(parts) == 1:
                r = self.subclass[parts[0]]
            if r:
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        self.instances[t.id] = r
        self.generic_visit(node)

    def _decorators(self, node) -> None:
        for d in node.decorator_list:
            target = d.func if isinstance(d, ast.Call) else d
            parts = _dotted(target)
            r = self._resolve(parts) if parts else None
            if r:
                self._use(r[0], r[1], "decorator", _call_args(d) if isinstance(d, ast.Call) else [], d.lineno)
                self._callees.add(id(target))
                if isinstance(d, ast.Call):
                    self._callees.add(id(d))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._decorators(node)
        saved = dict(self.instances)
        self.generic_visit(node)
        self.instances = saved

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        parts = _dotted(node.func)
        r = self._resolve(parts) if parts else None
        if r and r[1]:
            self._use(r[0], r[1], "function", _call_args(node), node.lineno)
            self._callees.add(id(node.func))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Load) and id(node) not in self._callees:
            parts = _dotted(node)
            r = self._resolve(parts) if parts else None
            if r and r[1] and len(parts) > 1:
                self._use(r[0], r[1], "attribute", [], node.lineno)
        self.generic_visit(node)


def _module_resolver(env: ProjectEnvironment):
    root = Path(env.root)
    local_tops = {Path(f.path).parts[0].removesuffix(".py") for f in env.files} | {
        p.stem for f in env.files for p in [Path(f.path)] if p.suffix == ".py"}

    def resolve(top: str) -> str | None:
        if top in _STDLIB or top in local_tops or (root / top).exists() or (root / f"{top}.py").exists():
            return None
        d = env.dep(top) or env.dep(top.replace("_", "-"))
        return d.name if d else norm_pkg(top)  # undeclared third-party import: audited (reported as NOT_FOUND)
    return resolve


def audit_python(env: ProjectEnvironment, path: str, text: str, lines: set[int] | None) -> list[dict]:
    from .verify_api import verify_planned_api
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    resolve = _module_resolver(env)
    v = _PyUsage(resolve)
    v.visit(tree)
    seen, out = set(), []
    for u in v.usages:
        if lines is not None and u["line"] not in lines:
            continue
        if u["kind"] == "import" and any(x["module"] == u["module"] and x["kind"] == "use" for x in v.usages):
            continue  # the uses of an imported name are audited instead of the bare import
        key = (u["module"], u["name"], tuple(u["args"]))
        if key in seen:
            continue
        seen.add(key)
        dep = resolve(u["module"].split(".")[0])
        pkg = PlannedPackage(package=dep, ecosystem="python", planned_apis=[PlannedAPI(
            import_path=u["module"], name=u["name"] or u["module"].split(".")[-1], type=u["type"] if u["name"] else "module",
            arguments=u["args"])])
        try:
            f = verify_planned_api(env, pkg, pkg.planned_apis[0]).to_dict()
        except Exception as e:  # never let the audit crash a run
            f = {"planned_api": f"{u['module']}.{u['name']}", "status": "UNCERTAIN", "explanation": f"audit error: {e}"}
        f.update({"file": path, "line": u["line"], "source": "audit"})
        out.append(f)
    return out


def audit_typescript(env: ProjectEnvironment, files: list[tuple[str, set[int] | None]], timeout: int = 60,
                     deps_root: str | None = None) -> list[dict]:
    node = shutil.which("node")
    if not node or not AUDITOR.exists() or not (AUDITOR.parent / "node_modules" / "typescript").is_dir():
        return [{"planned_api": "(typescript audit)", "status": "UNCERTAIN", "source": "audit",
                 "explanation": "TypeScript auditor unavailable (node or tools/ts-checker missing)"}]
    payload = {"projectRoot": env.root, "depsRoot": deps_root or env.root, "files": [{"path": p, "lines": sorted(l) if l is not None else None} for p, l in files]}
    try:
        p = subprocess.run([node, str(AUDITOR)], input=json.dumps(payload), capture_output=True, text=True, timeout=timeout,
                           cwd=env.root, env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "NODE_OPTIONS": "--max-old-space-size=1024"})
        rep = json.loads(p.stdout or "{}")
    except (subprocess.TimeoutExpired, ValueError, OSError) as e:
        return [{"planned_api": "(typescript audit)", "status": "UNCERTAIN", "source": "audit", "explanation": f"TypeScript audit failed: {e}"}]
    out = []
    for x in rep.get("findings", []):
        status = "DEPRECATED" if x["kind"] == "deprecated" else "NOT_FOUND" if x.get("code") in (2305, 2307, 2339, 2551, 2614, 2724) else "INCOMPATIBLE"
        out.append({"planned_api": f"{x.get('package') or '?'}:{x.get('api')}", "package": x.get("package"), "ecosystem": "node",
                    "installed_version": x.get("version"), "status": status, "file": x["file"], "line": x["line"],
                    "explanation": x["message"], "suggested_correction": x.get("deprecated") or None,
                    "verification_method": ["typescript_compiler_api(generated code)"], "source": "audit", "code": x.get("code")})
    return out


def audit_changes(env: ProjectEnvironment, sandbox: Path, changed: list[str], originals: dict[str, str | None]) -> dict:
    """Audit the changed files in `sandbox` (lines added relative to `originals`). Returns findings + summary."""
    findings: list[dict] = []
    ts_files: list[tuple[str, set[int] | None]] = []
    for rel in changed:
        p = sandbox / rel
        if not p.is_file():
            continue
        text = p.read_text(errors="ignore")
        lines = added_lines(originals.get(rel), text)
        if lines is not None and not lines:
            continue
        if p.suffix == ".py":
            findings += audit_python(env, rel, text, lines)
        elif p.suffix in (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".jsx"):
            ts_files.append((rel, lines))
    if ts_files:
        ts_env = ProjectEnvironment(**{**env.__dict__, "root": str(sandbox)})
        findings += audit_typescript(ts_env, ts_files, deps_root=env.root)
    problems = [f for f in findings if f.get("status") in PROBLEM]
    return {"findings": findings, "problems": problems, "checked": len(findings),
            "summary": f"{len(findings)} third-party API use(s) audited, {len(problems)} problem(s)"}
