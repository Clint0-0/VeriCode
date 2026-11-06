"""Module A - Repository Intelligence Engine (deterministic, no LLM)."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import db
from .security import is_sensitive_file

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".pytest_cache",
             ".mypy_cache", ".next", ".vericode_cache", "site-packages", ".tox", "coverage"}
SOURCE_EXT = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
              ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript"}
MANIFESTS = ["requirements.txt", "pyproject.toml", "poetry.lock", "uv.lock", "package.json",
             "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "tsconfig.json"]
FRAMEWORKS = {
    "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "pydantic": "Pydantic",
    "sqlalchemy": "SQLAlchemy", "react": "React", "next": "Next.js", "vue": "Vue",
    "express": "Express", "@nestjs/core": "NestJS", "svelte": "Svelte", "pytest": "pytest",
    "vitest": "Vitest", "jest": "Jest", "zod": "Zod",
}


def norm_pkg(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass
class Dependency:
    name: str
    ecosystem: str
    declared: str | None = None
    declared_in: str | None = None
    resolved: str | None = None
    resolved_in: str | None = None
    installed: str | None = None
    installed_path: str | None = None
    status: str = "unknown"  # ok | missing | not_installed_env_unavailable | mismatch


@dataclass
class FileInfo:
    path: str
    language: str
    size: int
    sha1: str
    symbols: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    is_test: bool = False


@dataclass
class ProjectEnvironment:
    root: str
    name: str
    languages: dict[str, int]
    frameworks: list[str]
    manifests: list[str]
    dependencies: list[Dependency]
    files: list[FileInfo]
    test_commands: list[list[str]]
    config_files: list[str]
    python_site_packages: str | None
    node_modules: str | None
    fingerprint: str
    warnings: list[str]

    def to_dict(self) -> dict:
        return asdict(self)

    def dep(self, name: str) -> Dependency | None:
        n = norm_pkg(name)
        return next((d for d in self.dependencies if norm_pkg(d.name) == n), None)


# --- manifest parsers --------------------------------------------------------
_REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)\s*(\[[^\]]*\])?\s*([^;#]*)")


def parse_requirements(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        m = _REQ_RE.match(line)
        if m:
            out[m.group(1)] = m.group(3).strip() or "*"
    return out


def parse_pyproject(text: str) -> dict[str, str]:
    data = tomllib.loads(text)
    out: dict[str, str] = {}
    for spec in data.get("project", {}).get("dependencies", []) or []:
        m = _REQ_RE.match(spec)
        if m:
            out[m.group(1)] = m.group(3).strip() or "*"
    for group in (data.get("project", {}).get("optional-dependencies", {}) or {}).values():
        for spec in group:
            m = _REQ_RE.match(spec)
            if m:
                out.setdefault(m.group(1), m.group(3).strip() or "*")
    poetry = data.get("tool", {}).get("poetry", {})
    for sect in ("dependencies", "dev-dependencies"):
        for k, v in (poetry.get(sect) or {}).items():
            if k.lower() == "python":
                continue
            out[k] = v if isinstance(v, str) else (v.get("version", "*") if isinstance(v, dict) else "*")
    return out


def parse_toml_lock(text: str) -> dict[str, str]:
    data = tomllib.loads(text)
    return {p["name"]: p["version"] for p in data.get("package", []) if "name" in p and "version" in p}


def parse_package_json(text: str) -> tuple[dict[str, str], dict]:
    data = json.loads(text)
    deps = {}
    for sect in ("dependencies", "devDependencies", "peerDependencies"):
        deps.update(data.get(sect) or {})
    return deps, data.get("scripts") or {}


def parse_package_lock(text: str) -> dict[str, str]:
    data = json.loads(text)
    out = {}
    for key, info in (data.get("packages") or {}).items():
        if key.startswith("node_modules/") and "version" in info:
            name = key.split("node_modules/")[-1]
            if key.count("node_modules/") == 1:
                out[name] = info["version"]
    if not out:
        for name, info in (data.get("dependencies") or {}).items():
            if "version" in info:
                out[name] = info["version"]
    return out


def parse_pnpm_lock(text: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r"^\s{2}'?/?((?:@[^/@\s]+/)?[^@/\s:']+)[@/](\d+\.\d+\.\d+[^:'(\s]*)", text, re.M):
        out.setdefault(m.group(1), m.group(2))
    return out


def parse_yarn_lock(text: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r'^"?((?:@[^@/\s]+/)?[^@\s"]+)@[^\n]*:\n\s+version:?\s+"?([^"\n]+)"?', text, re.M):
        out.setdefault(m.group(1), m.group(2).strip())
    return out


# --- installed environment inspection (static: reads metadata files only) -----
def find_site_packages(root: Path) -> Path | None:
    for venv in (".venv", "venv", "env"):
        for sp in sorted((root / venv).glob("lib/python*/site-packages")):
            return sp
        sp = root / venv / "Lib" / "site-packages"
        if sp.is_dir():
            return sp
    return None


def installed_python(sp: Path) -> dict[str, tuple[str, str]]:
    out = {}
    for meta in sp.glob("*.dist-info/METADATA"):
        name = version = None
        for line in meta.read_text(errors="ignore").splitlines()[:40]:
            if line.startswith("Name:"):
                name = line[5:].strip()
            elif line.startswith("Version:"):
                version = line[8:].strip()
            if name and version:
                break
        if name and version:
            out[norm_pkg(name)] = (version, str(meta.parent))
    return out


def installed_node(nm: Path) -> dict[str, tuple[str, str]]:
    out = {}
    cands = list(nm.glob("*/package.json")) + list(nm.glob("@*/*/package.json"))
    for pj in cands:
        try:
            d = json.loads(pj.read_text())
            out[d.get("name") or pj.parent.name] = (d.get("version", "?"), str(pj.parent))
        except Exception:
            continue
    return out


# --- file indexing -----------------------------------------------------------
def iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts) or not p.is_file():
            continue
        yield p, rel.as_posix()


def _py_symbols(text: str) -> tuple[list[str], list[str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], []
    syms, imps = [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            syms.append(node.name)
            if isinstance(node, ast.ClassDef):
                syms += [f"{node.name}.{n.name}" for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        elif isinstance(node, ast.Assign):
            syms += [t.id for t in node.targets if isinstance(t, ast.Name)]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imps += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imps.append(("." * node.level) + node.module)
    return syms, imps


_JS_SYM = re.compile(r"export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|interface|type)\s+([A-Za-z_$][\w$]*)")
_JS_IMP = re.compile(r"""(?:import[^'"]*from\s*|require\()\s*['"]([^'"]+)['"]""")


def index_file(p: Path, rel: str) -> FileInfo | None:
    lang = SOURCE_EXT.get(p.suffix)
    if not lang or p.stat().st_size > 400_000:
        return None
    text = p.read_text(errors="ignore")
    if lang == "Python":
        syms, imps = _py_symbols(text)
    else:
        syms, imps = _JS_SYM.findall(text), _JS_IMP.findall(text)
    name = p.name
    is_test = name.startswith("test_") or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".test.js")) or "tests" in rel.split("/")[:-1]
    return FileInfo(rel, lang, p.stat().st_size, hashlib.sha1(text.encode()).hexdigest(), syms, imps, is_test)


def fingerprint(root: Path) -> str:
    """Hash of manifests, lockfiles, installed-package metadata names and source file contents."""
    h = hashlib.sha1()
    for p, rel in iter_files(root):
        if p.name in MANIFESTS or p.suffix in SOURCE_EXT:
            h.update(rel.encode())
            h.update(hashlib.sha1(p.read_bytes()).digest())
    sp = find_site_packages(root)
    if sp:
        for meta in sorted(sp.glob("*.dist-info")):
            h.update(meta.name.encode())
    nm = root / "node_modules"
    if nm.is_dir():
        for pj in sorted(nm.glob("*/package.json"))[:2000]:
            h.update(pj.parent.name.encode())
            h.update(str(pj.stat().st_mtime_ns).encode())
    return h.hexdigest()


def inspect_project(root: Path, use_cache: bool = True) -> ProjectEnvironment:
    root = root.resolve()
    fp = fingerprint(root)
    key = f"env:{root}:{fp}"
    if use_cache:
        cached = db.cache_get(key)
        if cached:
            return _env_from_dict(cached)
    env = _inspect(root, fp)
    db.cache_set(key, env.to_dict(), ttl=7 * 86400)
    with db.tx() as c:
        c.execute(
            "INSERT INTO projects(id,path,name,fingerprint,environment_json,inspected_at) VALUES(?,?,?,?,?,strftime('%s','now')) "
            "ON CONFLICT(path) DO UPDATE SET fingerprint=excluded.fingerprint, environment_json=excluded.environment_json, inspected_at=excluded.inspected_at",
            (db.new_id("prj_"), str(root), root.name, fp, db.dumps(env.to_dict())),
        )
    return env


def _env_from_dict(d: dict) -> ProjectEnvironment:
    d = dict(d)
    d["dependencies"] = [Dependency(**x) for x in d["dependencies"]]
    d["files"] = [FileInfo(**x) for x in d["files"]]
    return ProjectEnvironment(**d)


def _inspect(root: Path, fp: str) -> ProjectEnvironment:
    warnings: list[str] = []
    langs: Counter = Counter()
    files: list[FileInfo] = []
    manifests: list[str] = []
    config_files: list[str] = []
    declared: dict[tuple[str, str], tuple[str, str]] = {}
    resolved: dict[tuple[str, str], tuple[str, str]] = {}
    scripts: dict = {}

    for p, rel in iter_files(root):
        if p.name in MANIFESTS:
            manifests.append(rel)
            try:
                t = p.read_text()
                if p.name == "requirements.txt":
                    for k, v in parse_requirements(t).items():
                        declared[("python", norm_pkg(k))] = (v, rel)
                elif p.name == "pyproject.toml":
                    for k, v in parse_pyproject(t).items():
                        declared.setdefault(("python", norm_pkg(k)), (v, rel))
                elif p.name in ("poetry.lock", "uv.lock"):
                    for k, v in parse_toml_lock(t).items():
                        resolved[("python", norm_pkg(k))] = (v, rel)
                elif p.name == "package.json" and rel.count("/") == 0:
                    deps, scripts = parse_package_json(t)
                    for k, v in deps.items():
                        declared[("node", k)] = (v, rel)
                elif p.name == "package-lock.json":
                    for k, v in parse_package_lock(t).items():
                        resolved[("node", k)] = (v, rel)
                elif p.name == "pnpm-lock.yaml":
                    for k, v in parse_pnpm_lock(t).items():
                        resolved.setdefault(("node", k), (v, rel))
                elif p.name == "yarn.lock":
                    for k, v in parse_yarn_lock(t).items():
                        resolved.setdefault(("node", k), (v, rel))
            except Exception as e:  # malformed manifest
                warnings.append(f"could not parse {rel}: {e}")
        elif p.name in (".env.example", "setup.cfg", "pytest.ini", "tox.ini", "vite.config.ts", "conftest.py", "Dockerfile") or is_sensitive_file(rel):
            config_files.append(rel + (" (sensitive: contents never read)" if is_sensitive_file(rel) else ""))
        fi = index_file(p, rel)
        if fi:
            files.append(fi)
            langs[fi.language] += 1

    sp = find_site_packages(root)
    inst_py = installed_python(sp) if sp else {}
    nm = root / "node_modules"
    inst_node = installed_node(nm) if nm.is_dir() else {}

    deps: list[Dependency] = []
    for (eco, name) in sorted(set(declared) | set(resolved)):
        d = Dependency(name=name, ecosystem=eco)
        if (eco, name) in declared:
            d.declared, d.declared_in = declared[(eco, name)]
        if (eco, name) in resolved:
            d.resolved, d.resolved_in = resolved[(eco, name)]
        inst = inst_py.get(name) if eco == "python" else inst_node.get(name)
        env_available = (sp is not None) if eco == "python" else nm.is_dir()
        if inst:
            d.installed, d.installed_path = inst
            d.status = "ok" if not d.resolved or d.resolved == d.installed else "mismatch"
        else:
            d.status = "missing" if env_available else "not_installed_env_unavailable"
        deps.append(d)
    if any(d.ecosystem == "python" for d in deps) and not sp:
        warnings.append("No Python virtualenv (.venv) found: installed versions unknown; declared ranges are NOT installed versions.")

    fw_names = {d.name for d in deps}
    frameworks = sorted({FRAMEWORKS[n] for n in fw_names if n in FRAMEWORKS})

    tests: list[list[str]] = []
    has_py_tests = any(f.is_test and f.language == "Python" for f in files)
    if has_py_tests or ("python", "pytest") in declared or "pytest" in inst_py:
        tests.append(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    if "test" in scripts:
        tests.append(["npm", "test"])
    if "typecheck" in scripts:
        tests.append(["npm", "run", "typecheck"])

    return ProjectEnvironment(
        root=str(root), name=root.name, languages=dict(langs), frameworks=frameworks,
        manifests=manifests, dependencies=deps, files=files, test_commands=tests,
        config_files=config_files, python_site_packages=str(sp) if sp else None,
        node_modules=str(nm) if nm.is_dir() else None, fingerprint=fp, warnings=warnings,
    )


# --- relevant-file selection --------------------------------------------------
_STOP = set("the a an and or to of in for on with into from by is are be this that it as at add make use new should "
            "create update implement function method class file code test tests support when then".split())


def _terms(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]+", text)
    out = set()
    for w in words:
        for part in re.split(r"_|(?<=[a-z])(?=[A-Z])", w):
            p = part.lower()
            if len(p) > 2 and p not in _STOP:
                out.add(p[:-1] if p.endswith("s") and len(p) > 4 else p)
    return out


def select_relevant_files(env: ProjectEnvironment, task: str, limit: int = 6) -> list[dict]:
    """Score files by overlap of task terms with path, symbols and imports. Returns reasons."""
    # drop terms shared by most files (e.g. the package name): they carry no signal
    n = max(1, len(env.files))
    df: Counter = Counter()
    for f in env.files:
        df.update(_terms(f.path.replace("/", " ").replace(".", " ")) | _terms(" ".join(f.symbols)))
    tt = {t for t in _terms(task) if df[t] / n <= 0.5 or n < 4}
    idents = {w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", task) if "_" in w or re.search(r"[a-z][A-Z]", w)}
    scored = []
    for f in env.files:
        path_terms = _terms(f.path.replace("/", " ").replace(".", " "))
        sym_terms = _terms(" ".join(f.symbols))
        reasons, score = [], 0.0
        pm = tt & path_terms
        if pm:
            score += 3 * len(pm)
            reasons.append(f"path matches {sorted(pm)}")
        sm = tt & sym_terms
        if sm:
            score += 2 * len(sm)
            reasons.append(f"defines symbols matching {sorted(sm)[:5]}")
        exact = idents & {sym.split(".")[-1] for sym in f.symbols} | idents & {sym.split(".")[0] for sym in f.symbols}
        if exact:
            score += 5 * len(exact)
            reasons.append(f"defines exact identifier(s) named in task {sorted(exact)}")
        im = tt & _terms(" ".join(f.imports))
        if im:
            score += 1 * len(im)
            reasons.append(f"imports {sorted(im)[:5]}")
        if score:
            scored.append({"path": f.path, "score": score, "reasons": reasons, "is_test": f.is_test})
    scored.sort(key=lambda x: -x["score"])
    top = scored[0]["score"] if scored else 0
    chosen = [s for s in scored if not s["is_test"] and s["score"] >= 0.4 * top][:limit]
    # add tests that reference chosen modules
    chosen_mods = {Path(c["path"]).stem for c in chosen}
    for f in env.files:
        if f.is_test and any(m in " ".join(f.imports) or m in f.path for m in chosen_mods):
            if all(c["path"] != f.path for c in chosen):
                chosen.append({"path": f.path, "score": 0.5, "reasons": ["test covering selected module"], "is_test": True})
    return chosen
