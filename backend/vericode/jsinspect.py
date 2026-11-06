"""Module C (JS/TS) - verify imports/exports against installed node_modules.

Uses package.json `exports`/`types`/`typings`, follows `export * from` / `export {..} from` in .d.ts
files, and extracts function parameter names from declarations. When the project has `typescript`
installed, a TS-compiler-API check (node subprocess, timeout) type-checks the planned import.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class JsSymbolInfo:
    found: bool
    qualname: str
    package_version: str | None = None
    kind: str | None = None
    location: str | None = None
    params: list[dict] = field(default_factory=list)
    accepts_var_kwargs: bool = False
    deprecated: str | None = None
    rejected_kwargs: dict = field(default_factory=dict)
    migration_hint: str | None = None
    method: str = "static_dts"
    note: str | None = None
    resolution_path: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _pkg_dir(nm: Path, spec: str) -> tuple[Path | None, str]:
    parts = spec.split("/")
    name = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
    sub = spec[len(name):].lstrip("/")
    d = nm / name
    return (d if d.is_dir() else None), sub


def _types_entry(pkg: Path, sub: str) -> Path | None:
    pj = json.loads((pkg / "package.json").read_text())
    key = "./" + sub if sub else "."
    exp = pj.get("exports")
    cands: list[str] = []

    def collect(e):
        if isinstance(e, str):
            cands.append(e)
        elif isinstance(e, dict):
            for k in ("types", "typings", "import", "require", "default", "node"):
                if k in e:
                    collect(e[k])
    if isinstance(exp, dict) and (key in exp or not any(k.startswith(".") for k in exp)):
        collect(exp.get(key, exp))
    elif isinstance(exp, str) and not sub:
        cands.append(exp)
    if not sub:
        for k in ("types", "typings", "module", "main"):
            if pj.get(k):
                cands.append(pj[k])
        cands += ["index.d.ts", "index.js"]
    else:
        cands += [f"{sub}.d.ts", f"{sub}/index.d.ts", f"{sub}.js"]
    for c in cands:
        p = (pkg / c).resolve()
        for alt in (p, p.with_suffix(".d.ts"), Path(str(p).replace(".mjs", ".d.mts")), Path(str(p).replace(".js", ".d.ts")),
                    Path(str(p).replace(".cjs", ".d.cts"))):
            if alt.is_file():
                return alt
    types_pkg = pkg.parent.parent / "@types" / pkg.name if not pkg.name.startswith("@") else None
    if types_pkg and (types_pkg / "index.d.ts").is_file():
        return types_pkg / "index.d.ts"
    return None


_DECL = r"export\s+(?:declare\s+)?(?:default\s+)?(?:abstract\s+)?(function|class|const|let|var|interface|type|enum|namespace)\s+{name}\b"


def _find(file: Path, name: str, depth: int, trail: list[str]):
    if depth > 10 or not file.is_file():
        return None
    text = file.read_text(errors="ignore")
    trail.append(file.name)
    m = re.search(_DECL.format(name=re.escape(name)), text)
    if m:
        return file, text, m
    for em in re.finditer(r"export\s*(?:type\s*)?\{([^}]*)\}\s*(?:from\s*['\"]([^'\"]+)['\"])?", text):
        for item in em.group(1).split(","):
            bits = [b.strip() for b in item.replace("type ", "").split(" as ")]
            if bits and bits[-1] == name:
                orig = bits[0]
                if em.group(2):
                    nxt = _rel_module(file, em.group(2))
                    if nxt:
                        return _find(nxt, orig, depth + 1, trail)
                else:
                    m2 = re.search(r"(?:declare\s+)?(function|class|const|interface|type|enum)\s+" + re.escape(orig) + r"\b", text)
                    if m2:
                        return file, text, m2
    for sm in re.finditer(r"export\s*\*\s*from\s*['\"]([^'\"]+)['\"]", text):
        nxt = _rel_module(file, sm.group(1))
        if nxt:
            r = _find(nxt, name, depth + 1, trail)
            if r:
                return r
    return None


def _rel_module(file: Path, spec: str) -> Path | None:
    if not spec.startswith("."):
        return None
    base = (file.parent / spec)
    s = str(base)
    for c in (s, s.replace(".js", ".d.ts"), s.replace(".mjs", ".d.mts"), s + ".d.ts", s + "/index.d.ts", s.replace(".js", "") + ".d.ts"):
        p = Path(c)
        if p.is_file() and (p.suffix == ".ts" or p.name.endswith(".d.mts") or p.name.endswith(".d.cts")):
            return p
    return None


def resolve(node_modules: Path, spec: str, qualname: str) -> JsSymbolInfo:
    info = JsSymbolInfo(found=False, qualname=f"{spec}:{qualname}")
    pkg, sub = _pkg_dir(node_modules, spec)
    if not pkg:
        info.note = f"package {spec!r} not installed in node_modules"
        return info
    info.package_version = json.loads((pkg / "package.json").read_text()).get("version")
    entry = _types_entry(pkg, sub)
    if not entry:
        info.note = "no type declarations found; export availability cannot be statically verified"
        info.method = "unverifiable"
        return info
    if not qualname:
        info.found, info.kind, info.location = True, "module", str(entry.relative_to(node_modules))
        return info
    head = qualname.split(".")[0]
    hit = _find(entry, head, 0, info.resolution_path)
    if not hit:
        return info
    f, text, m = hit
    line = text[: m.start()].count("\n") + 1
    info.found, info.kind = True, m.group(1)
    info.location = f"{f.relative_to(node_modules)}:{line}"
    pre = text[max(0, m.start() - 600): m.start()]
    dep = re.search(r"@deprecated\s*([^\n*]*)", pre.split("*/")[-2] if pre.count("*/") >= 1 else "")
    if dep and pre.rstrip().endswith("*/"):
        info.deprecated = dep.group(1).strip() or "marked @deprecated"
    if info.kind == "function":
        sig = re.match(r"[^(]*\(([^)]*)\)", text[m.end(): m.end() + 800])
        if sig:
            for p in [x.strip() for x in sig.group(1).split(",") if x.strip()]:
                nm = re.match(r"(\.\.\.)?([A-Za-z_$][\w$]*)(\?)?", p)
                if nm:
                    info.params.append({"name": nm.group(2), "required": not nm.group(3) and not nm.group(1), "kind": "rest" if nm.group(1) else "positional"})
    if "." in qualname and info.kind in ("class", "interface"):
        member = qualname.split(".", 1)[1]
        body = text[m.end(): m.end() + 20000]
        if not re.search(r"\b" + re.escape(member) + r"\s*[(<:?]", body):
            info.found = False
            info.note = f"member {member} not found in declaration of {head}"
    return info


TSC_SCRIPT = r"""
const ts = require(process.argv[2]);
const src = process.argv[3];
const opts = {noEmit: true, strict: false, moduleResolution: ts.ModuleResolutionKind.Node10 ?? 2, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020, skipLibCheck: true, esModuleInterop: true};
const host = ts.createCompilerHost(opts);
const fname = process.cwd() + '/__vericode_check__.ts';
const orig = host.getSourceFile;
host.getSourceFile = (f, l) => f === fname ? ts.createSourceFile(f, src, l) : orig(f, l);
host.fileExists = ((fe) => (f) => f === fname || fe(f))(host.fileExists);
const prog = ts.createProgram([fname], opts, host);
const d = ts.getPreEmitDiagnostics(prog).filter(x => x.file && x.file.fileName === fname);
console.log(JSON.stringify(d.map(x => ts.flattenDiagnosticMessageText(x.messageText, '\n'))));
"""


def tsc_check(project_root: Path, snippet: str, timeout: int = 30) -> dict:
    """Type-check a tiny snippet (e.g. `import { x } from 'pkg'; x(1)`) with the project's own TypeScript."""
    ts = project_root / "node_modules" / "typescript"
    node = shutil.which("node")
    if not ts.is_dir() or not node:
        return {"available": False}
    try:
        p = subprocess.run([node, "-e", TSC_SCRIPT, str(ts), snippet], cwd=str(project_root), capture_output=True,
                           text=True, timeout=timeout, env={"PATH": "/usr/bin:/bin"})
        return {"available": True, "diagnostics": json.loads(p.stdout or "[]")}
    except Exception as e:
        return {"available": True, "error": str(e)}


# ----------------------------------------------------------------------------- TypeScript compiler API
CHECKER = Path(__file__).resolve().parents[2] / "tools" / "ts-checker" / "check.cjs"


def ts_checker_available() -> bool:
    return bool(shutil.which("node")) and CHECKER.exists() and (CHECKER.parent / "node_modules" / "typescript").is_dir()


def ts_compiler_check(project_root: Path, module: str, name: str, member: str = "", args: list[str] | None = None,
                      timeout: int = 45) -> dict:
    """Resolve the module with the project's node_modules and check exports, signatures, @deprecated and
    (when `args` are given as TypeScript expressions) the actual call with the TypeScript type checker.
    Runs VeriCode's pinned TypeScript in a subprocess (scrubbed env, timeout); the user project is not modified."""
    if not ts_checker_available():
        return {"available": False, "error": "TypeScript checker not installed (run scripts/setup.sh: npm ci in tools/ts-checker)"}
    payload = {"projectRoot": str(project_root), "module": module, "name": name, "member": member}
    if args is not None:
        payload["args"] = [a for a in args if isinstance(a, str)][:10]
    try:
        p = subprocess.run([shutil.which("node"), str(CHECKER)], input=json.dumps(payload), capture_output=True, text=True,
                           timeout=timeout, cwd=str(project_root), env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "NODE_OPTIONS": "--max-old-space-size=1024"})
        out = json.loads(p.stdout or "{}")
        out["available"] = True
        return out
    except subprocess.TimeoutExpired:
        return {"available": True, "error": f"TypeScript check timed out after {timeout}s"}
    except (ValueError, OSError) as e:
        return {"available": True, "error": f"TypeScript checker failed: {e}"}
