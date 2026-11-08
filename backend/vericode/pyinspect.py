"""Module C (Python) - static verification of API usage against INSTALLED package source.

No user/package code is imported or executed by default. Optional runtime introspection runs in an
isolated subprocess (project interpreter, -I, timeout, scrubbed env) only when static analysis fails.
"""
from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass
class SymbolInfo:
    found: bool
    qualname: str
    kind: str | None = None  # function | class | method | variable | module
    location: str | None = None
    params: list[dict] = field(default_factory=list)
    accepts_var_kwargs: bool = False
    accepts_var_args: bool = False
    deprecated: str | None = None
    rejected_kwargs: dict[str, str] = field(default_factory=dict)
    migration_hint: str | None = None
    doc: str | None = None
    resolution_path: list[str] = field(default_factory=list)
    method: str = "static_ast"
    note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1024)
def _parse_cached(path: str, mtime_ns: int, size: int) -> ast.Module | None:
    try:
        return ast.parse(Path(path).read_text(errors="ignore"))
    except (SyntaxError, OSError):
        return None


def _parse(path: str) -> ast.Module | None:
    """AST cache keyed by (path, mtime, size): an upgraded/reinstalled package is re-parsed, never served stale."""
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return _parse_cached(path, st.st_mtime_ns, st.st_size)


def module_file(sp: Path, module: str) -> Path | None:
    parts = module.split(".")
    base = sp.joinpath(*parts)
    for cand in (base / "__init__.py", base.with_suffix(".py"), base / "__init__.pyi", base.with_suffix(".pyi")):
        if cand.is_file():
            return cand
    return None


def _resolve_relative(current_module: str, is_pkg: bool, level: int, mod: str | None) -> str:
    if level == 0:
        return mod or ""
    parts = current_module.split(".")
    if not is_pkg:
        parts = parts[:-1]
    if level > 1:
        parts = parts[: len(parts) - (level - 1)]
    return ".".join(parts + ([mod] if mod else []))


def _walk_toplevel(body):
    """Yield top-level statements, descending into if/try blocks (TYPE_CHECKING, version guards)."""
    for node in body:
        yield node
        if isinstance(node, ast.If):
            yield from _walk_toplevel(node.body)
            yield from _walk_toplevel(node.orelse)
        elif isinstance(node, ast.Try):
            yield from _walk_toplevel(node.body)
            for h in node.handlers:
                yield from _walk_toplevel(h.body)


def _decorator_name(d: ast.expr) -> str:
    if isinstance(d, ast.Call):
        d = d.func
    if isinstance(d, ast.Attribute):
        return d.attr
    if isinstance(d, ast.Name):
        return d.id
    return ""


def _deprecation(node) -> str | None:
    for d in getattr(node, "decorator_list", []):
        if _decorator_name(d) == "deprecated":
            if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant):
                return str(d.args[0].value)
            return "marked @deprecated"
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _decorator_name(sub.func) == "warn":
            txt = " ".join(str(a.value) for a in sub.args if isinstance(a, ast.Constant) and isinstance(a.value, str))
            cats = " ".join(ast.unparse(a) for a in sub.args[1:]) + " ".join(ast.unparse(k.value) for k in sub.keywords)
            if "Deprecat" in cats or "deprecat" in txt.lower():
                # only treat as whole-function deprecation if the warn is at function top level
                if any(isinstance(s, ast.Expr) and s.value is sub for s in getattr(node, "body", [])):
                    return txt or "emits DeprecationWarning"
    return None


def _rejected_kwargs(fn: ast.FunctionDef) -> dict[str, str]:
    """Detect `x = kwargs.pop('name', ...)` followed by `if x ...: raise Err('msg')`."""
    out: dict[str, str] = {}
    kwname = fn.args.kwarg.arg if fn.args.kwarg else None
    if not kwname:
        return out
    popped: dict[str, str] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            c = node.value
            if (isinstance(c.func, ast.Attribute) and c.func.attr in ("pop", "get") and isinstance(c.func.value, ast.Name)
                    and c.func.value.id == kwname and c.args and isinstance(c.args[0], ast.Constant)
                    and isinstance(node.targets[0], ast.Name)):
                popped[node.targets[0].id] = str(c.args[0].value)
    for node in ast.walk(fn):
        if isinstance(node, ast.If):
            names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
            hit = names & set(popped)
            raises = [s for s in node.body if isinstance(s, ast.Raise)]
            if hit and raises:
                msg = " ".join(str(n.value) for n in ast.walk(raises[0]) if isinstance(n, ast.Constant) and isinstance(n.value, str))
                for v in hit:
                    out[popped[v]] = msg[:300] or "rejected by explicit raise"
        # `if 'name' in kwargs: raise`
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Constant):
            comp = node.test.comparators[0] if node.test.comparators else None
            if isinstance(comp, ast.Name) and comp.id == kwname and any(isinstance(s, ast.Raise) for s in node.body):
                r = next(s for s in node.body if isinstance(s, ast.Raise))
                msg = " ".join(str(n.value) for n in ast.walk(r) if isinstance(n, ast.Constant) and isinstance(n.value, str))
                out[str(node.test.left.value)] = msg[:300] or "rejected by explicit raise"
    return out


def _params(fn: ast.FunctionDef) -> list[dict]:
    a = fn.args
    out = []
    pos = a.posonlyargs + a.args
    defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    for arg, d in zip(pos, defaults):
        out.append({"name": arg.arg, "kind": "positional", "required": d is None,
                    "annotation": ast.unparse(arg.annotation) if arg.annotation else None})
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        out.append({"name": arg.arg, "kind": "keyword_only", "required": d is None,
                    "annotation": ast.unparse(arg.annotation) if arg.annotation else None})
    return out


def _is_overload(fn) -> bool:
    return any(_decorator_name(d) == "overload" for d in fn.decorator_list)


class PyResolver:
    def __init__(self, site_packages: Path):
        self.sp = site_packages

    def _rel(self, p: Path, line: int | None = None) -> str:
        try:
            r = p.relative_to(self.sp).as_posix()
        except ValueError:
            r = str(p)
        return f"{r}:{line}" if line else r

    def find_in_module(self, module: str, name: str, depth: int = 0, trail: list[str] | None = None):
        """Return (node, file, module) for a top-level name, following re-exports."""
        trail = trail if trail is not None else []
        if depth > 8:
            return None
        f = module_file(self.sp, module)
        if not f:
            return None
        tree = _parse(str(f))
        if tree is None:
            return None
        is_pkg = f.name.startswith("__init__")
        trail.append(self._rel(f))
        defs = []
        star_imports = []
        for node in _walk_toplevel(tree.body):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                defs.append(node)
            elif isinstance(node, ast.ImportFrom):
                target_mod = _resolve_relative(module, is_pkg, node.level, node.module)
                for alias in node.names:
                    if alias.name == "*":
                        star_imports.append(target_mod)
                    elif (alias.asname or alias.name) == name:
                        sub = self.find_in_module(target_mod, alias.name, depth + 1, trail)
                        if sub:
                            return sub
                        # may be a submodule
                        if module_file(self.sp, f"{target_mod}.{alias.name}"):
                            return ("module", module_file(self.sp, f"{target_mod}.{alias.name}"), f"{target_mod}.{alias.name}")
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Name) and t.id == "_dynamic_imports" and isinstance(node.value, ast.Dict):
                        for k, v in zip(node.value.keys, node.value.values):
                            if isinstance(k, ast.Constant) and k.value == name and isinstance(v, ast.Tuple):
                                vals = [e.value for e in v.elts if isinstance(e, ast.Constant)]
                                if len(vals) == 2:
                                    rel = vals[1]
                                    lvl = len(rel) - len(rel.lstrip("."))
                                    tm = _resolve_relative(module, is_pkg, lvl, rel.lstrip(".") or None)
                                    sub = self.find_in_module(tm, name, depth + 1, trail)
                                    if sub:
                                        return sub
                    elif isinstance(t, ast.Name) and t.id == name:
                        defs.append(node)
        if defs:
            real = [d for d in defs if not (isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_overload(d))]
            return (real[-1] if real else defs[-1], f, module, defs)
        for sm in star_imports:
            sub = self.find_in_module(sm, name, depth + 1, trail)
            if sub:
                return sub
        sub_mod = module_file(self.sp, f"{module}.{name}")
        if sub_mod:
            return ("module", sub_mod, f"{module}.{name}")
        return None

    def migration_hint(self, top: str, name: str) -> str | None:
        """Search the installed package for package-provided migration/rename messages about `top:name`."""
        key = f"{top}:{name}"
        pkg_dir = self.sp / top
        if not pkg_dir.is_dir():
            return None
        for f in pkg_dir.rglob("*.py"):
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            if key not in text:
                continue
            tree = _parse(str(f))
            if tree is None:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    for k, v in zip(node.keys, node.values):
                        if isinstance(k, ast.Constant) and k.value == key and isinstance(v, ast.Constant):
                            return f"package migration map ({self._rel(f, node.lineno)}): {key} -> {v.value}"
                if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
                    consts = [c.value for c in ast.walk(node.test) if isinstance(c, ast.Constant)]
                    if key in consts:
                        msgs = [c.value for c in ast.walk(ast.Module(body=node.body, type_ignores=[]))
                                if isinstance(c, ast.Constant) and isinstance(c.value, str) and len(c.value) > 15]
                        if msgs:
                            return f"package migration message ({self._rel(f, node.lineno)}): {''.join(msgs)[:300]}"
        return None

    def resolve(self, module: str, qualname: str) -> SymbolInfo:
        parts = qualname.split(".") if qualname else []
        info = SymbolInfo(found=False, qualname=f"{module}.{qualname}" if qualname else module)
        if not parts:
            f = module_file(self.sp, module)
            info.found, info.kind = bool(f), "module"
            info.location = self._rel(f) if f else None
            return info
        trail: list[str] = []
        hit = self.find_in_module(module, parts[0], trail=trail)
        info.resolution_path = trail
        if not hit:
            info.migration_hint = self.migration_hint(module.split(".")[0], parts[0])
            return info
        node, f, mod = hit[0], hit[1], hit[2]
        if node == "module":
            info.found, info.kind, info.location = True, "module", self._rel(f)
            if len(parts) > 1:
                return self.resolve(mod, ".".join(parts[1:]))
            return info
        if len(parts) > 1:
            if not isinstance(node, ast.ClassDef):
                info.note = f"{parts[0]} is not a class"
                return info
            meth = self._find_method(node, f, mod, parts[1])
            if not meth:
                info.note = f"{parts[0]} has no attribute {parts[1]} in installed source (checked class and resolvable bases)"
                return info
            node, f = meth
            info.kind = "method"
        self._fill(info, node, f)
        return info

    def _find_method(self, cls: ast.ClassDef, f: Path, mod: str, name: str, depth: int = 0):
        cands = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
        if cands:
            real = [c for c in cands if not _is_overload(c)]
            return (real[-1] if real else cands[-1]), f
        for n in cls.body:  # class attributes
            if isinstance(n, (ast.Assign, ast.AnnAssign)):
                tg = n.targets if isinstance(n, ast.Assign) else [n.target]
                if any(isinstance(t, ast.Name) and t.id == name for t in tg):
                    return n, f
        if depth > 5:
            return None
        for base in cls.bases:
            bname = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else None)
            if not bname or bname in ("object", "Generic", "Protocol"):
                continue
            hit = self.find_in_module(mod, bname)
            if hit and isinstance(hit[0], ast.ClassDef):
                r = self._find_method(hit[0], hit[1], hit[2], name, depth + 1)
                if r:
                    return r
        return None

    def _fill(self, info: SymbolInfo, node, f: Path) -> None:
        info.found = True
        info.location = self._rel(f, getattr(node, "lineno", None))
        if isinstance(node, ast.ClassDef):
            info.kind = info.kind or "class"
            init = next((n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None)
            info.deprecated = _deprecation(node)
            if init:
                info.params = [p for p in _params(init) if p["name"] != "self"]
                info.accepts_var_kwargs = init.args.kwarg is not None
                info.rejected_kwargs = _rejected_kwargs(init)
            else:
                info.accepts_var_kwargs = True
                info.note = "no explicit __init__; constructor arguments derived from fields/metaclass are not statically checked"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.kind = info.kind or "function"
            info.params = [p for p in _params(node) if p["name"] not in ("self", "cls")]
            info.accepts_var_kwargs = node.args.kwarg is not None
            info.accepts_var_args = node.args.vararg is not None
            info.deprecated = _deprecation(node)
            info.rejected_kwargs = _rejected_kwargs(node)
        else:
            info.kind = info.kind or "variable"
        doc = ast.get_docstring(node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else None
        info.doc = doc.strip().splitlines()[0][:200] if doc else None


def check_arguments(info: SymbolInfo, args: list[str]) -> list[dict]:
    out = []
    names = {p["name"] for p in info.params}
    positional_slots = sum(1 for p in info.params if p.get("kind", "positional") == "positional" and p["name"] not in ("self", "cls"))
    used_positional = 0
    for raw in args:
        keyword = "=" in raw and raw.split("=")[0].strip().isidentifier()
        a = raw.split("=")[0].strip() if keyword else raw.strip()
        if not a or a.startswith("*"):
            continue
        if not keyword and not a.isidentifier():
            # a positional VALUE ('due', 3, None), not a parameter name
            used_positional += 1
            ok = info.accepts_var_args or used_positional <= positional_slots
            out.append({"argument": a, "status": "supported" if ok else "unsupported",
                        "detail": "positional value" + (" (accepted by *args)" if info.accepts_var_args else "")
                        if ok else f"more positional values than the {positional_slots} positional parameter(s)"})
            continue
        if a in info.rejected_kwargs:
            out.append({"argument": a, "status": "rejected", "detail": info.rejected_kwargs[a]})
        elif a in names:
            out.append({"argument": a, "status": "supported", "detail": "present in installed signature"})
        elif info.accepts_var_kwargs:
            out.append({"argument": a, "status": "uncertain", "detail": "not a named parameter; would be swallowed by **kwargs"})
        elif info.accepts_var_args and not keyword:
            out.append({"argument": a, "status": "uncertain", "detail": "not a parameter name; plausible as a positional value for *args"})
        else:
            out.append({"argument": a, "status": "unsupported", "detail": "not in installed signature and no **kwargs"})
    return out


RUNTIME_SCRIPT = r"""
import importlib, inspect, json, sys
mod, qual = sys.argv[1], sys.argv[2]
try:
    obj = importlib.import_module(mod)
    for part in [p for p in qual.split('.') if p]:
        obj = getattr(obj, part)
    try:
        sig = inspect.signature(obj)
        params = [{"name": p.name, "kind": str(p.kind), "required": p.default is inspect._empty} for p in sig.parameters.values()]
    except (TypeError, ValueError):
        params = None
    print(json.dumps({"found": True, "params": params}))
except Exception as e:
    print(json.dumps({"found": False, "error": type(e).__name__ + ": " + str(e)[:300]}))
"""


def runtime_introspect(python_exe: Path, module: str, qualname: str, timeout: int = 10) -> dict:
    """Isolated runtime check: separate process, -I (isolated mode), scrubbed env, timeout, and no network
    (user+net namespace) where `unshare -rn` works."""
    from .security import network_isolation_available
    prefix = ["unshare", "-rn"] if network_isolation_available() else []  # no network for imported package code when supported
    try:
        p = subprocess.run(prefix + [str(python_exe), "-I", "-c", RUNTIME_SCRIPT, module, qualname],
                           capture_output=True, text=True, timeout=timeout,
                           env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
        return json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {"found": False, "error": p.stderr[-300:]}
    except subprocess.TimeoutExpired:
        return {"found": False, "error": f"runtime introspection timed out after {timeout}s"}
    except Exception as e:
        return {"found": False, "error": str(e)}
