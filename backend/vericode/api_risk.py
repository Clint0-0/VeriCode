"""Adaptive execution gate: decide whether a task needs the planner + API pre-flight.

Conservative by construction. The fast path (no planner call) is chosen only when there is positive evidence
that the task does not involve third-party APIs:

* the project has a test command (otherwise nothing could catch a wrong change);
* the task text names no installed/declared dependency, no import name of one, and no identifier the project
  imports from a third-party package (for example `BaseModel`, `z`, `field_validator`);
* the task text contains no dependency-related wording (library, package, upgrade, migrate, deprecated, import,
  version, SDK, install ...);
* the task text contains no capability words of an installed dependency (for pydantic: model, validator, schema,
  serialize ...; for zod: schema, validate, parse ...). This list is a deliberate over-approximation.

Any of these signals sends the task down the full verification path ("high" risk). The fast path never skips
verification of the code itself: after every coder attempt the generated code is audited locally against the
installed packages (api_audit.py), so a third-party API that slips through is still checked, at no token cost.
"""
from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .repo_intel import ProjectEnvironment, norm_pkg

DEPENDENCY_WORDS = re.compile(
    r"\b(librar(?:y|ies)|packages?|dependenc(?:y|ies)|upgrad\w*|migrat\w*|deprecat\w*|imports?|versions?|sdks?|install\w*|"
    r"third[- ]party|framework|plugin|api client|http|https|requests?|endpoints?|fetch|async\s+client)\b", re.I)

# Capability vocabulary of common dependencies. Over-approximation on purpose: a false "high" only costs the
# planner call; a false "low" is still caught by the post-generation audit.
CAPABILITY_WORDS: dict[str, tuple[str, ...]] = {
    "pydantic": ("model", "models", "validator", "validators", "validate", "validation", "schema", "serialize",
                 "serializer", "serialization", "field", "fields", "settings", "config", "json", "dump", "parse"),
    "zod": ("schema", "schemas", "validate", "validation", "validator", "parse", "safeparse", "refine", "transform",
            "coerce", "enum", "infer"),
    "vitest": ("mock", "spy", "snapshot", "fixture", "timer", "fake timers"),
    "pytest": ("fixture", "fixtures", "parametrize", "monkeypatch", "mark", "marker"),
    "httpx": ("http", "request", "client", "fetch", "download", "timeout", "retry"),
    "requests": ("http", "request", "fetch", "download", "session"),
    "fastapi": ("endpoint", "route", "router", "dependency", "middleware", "api"),
    "sqlalchemy": ("query", "session", "orm", "table", "column", "migration"),
    "date-fns": ("date", "dates", "format", "parse", "interval", "duration", "timezone"),
    "dayjs": ("date", "dates", "format", "timezone"),
    "lodash": ("debounce", "throttle", "clone", "merge"),
    "express": ("route", "router", "middleware", "endpoint"),
}
# test runners are always installed in benchmark projects; their capability words only matter for test tasks
TEST_RUNNERS = {"pytest", "vitest", "jest", "mocha"}
_TS_IMPORT = re.compile(r"""import\s+(?:type\s+)?(?P<clause>[^'";]+?)\s+from\s+['"](?P<mod>[^'"]+)['"]""")


@dataclass
class RiskAssessment:
    risk: str  # "low" -> fast path allowed; "high" -> full verification path
    reasons: list[str] = field(default_factory=list)
    matched: dict[str, list[str]] = field(default_factory=dict)
    third_party_identifiers: list[str] = field(default_factory=list)

    @property
    def fast_path(self) -> bool:
        return self.risk == "low"

    def to_dict(self) -> dict:
        return {**asdict(self), "fast_path": self.fast_path}


def _words(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", text)}


def third_party_imports(env: ProjectEnvironment, include_tests: bool = True) -> dict[str, set[str]]:
    """identifier -> packages it is imported from, across project source files (AST for Python, regex for TS/JS).
    With include_tests=False, imports that appear only in test files (`it`, `expect`, `describe` ...) are left out."""
    deps = {norm_pkg(d.name) for d in env.dependencies}
    out: dict[str, set[str]] = {}
    root = Path(env.root)

    def add(name: str, pkg: str) -> None:
        out.setdefault(name, set()).add(pkg)

    for f in env.files:
        if f.is_test and not include_tests:
            continue
        p = root / f.path
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        if f.language == "Python":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    top = norm_pkg(node.module.split(".")[0])
                    if top in deps:
                        for a in node.names:
                            add(a.asname or a.name, top)
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        top = norm_pkg(a.name.split(".")[0])
                        if top in deps:
                            add(a.asname or a.name.split(".")[0], top)
        else:
            for m in _TS_IMPORT.finditer(text):
                mod = m.group("mod")
                if mod.startswith("."):
                    continue
                pkg = "/".join(mod.split("/")[:2]) if mod.startswith("@") else mod.split("/")[0]
                if norm_pkg(pkg) not in deps:
                    continue
                clause = m.group("clause")
                for name in re.findall(r"[A-Za-z_$][\w$]*", re.sub(r"\b\w+\s+as\s+", "", clause.replace("* as", ""))):
                    if name not in ("type",):
                        add(name, norm_pkg(pkg))
    return out


def assess(env: ProjectEnvironment, task: str) -> RiskAssessment:
    reasons: list[str] = []
    matched: dict[str, list[str]] = {}
    words = _words(task)
    lower = task.lower()

    if not env.test_commands:
        reasons.append("no test command detected: a change could not be validated, so the full path is used")

    dep_hits = []
    for d in env.dependencies:
        names = {d.name.lower(), norm_pkg(d.name), d.name.lower().replace("-", "_"), d.name.split("/")[-1].lower()}
        if any(re.search(rf"(?<![\w@/-]){re.escape(n)}(?![\w-])", lower) for n in names if n):
            dep_hits.append(d.name)
    if dep_hits:
        matched["dependency_names"] = sorted(set(dep_hits))
        reasons.append(f"task names installed/declared dependencies: {sorted(set(dep_hits))}")

    is_test_task = bool(re.search(r"\b(unit[- ]?tests?|tests?|spec)\b", lower))
    imports = third_party_imports(env, include_tests=is_test_task)
    id_hits = sorted({i for i in imports if re.search(rf"(?<![\w$]){re.escape(i)}(?![\w$])", task)})
    if id_hits:
        matched["third_party_identifiers"] = id_hits
        reasons.append(f"task names identifiers the project imports from third-party packages: {id_hits}")

    kw = sorted({m.group(0).lower() for m in DEPENDENCY_WORDS.finditer(task)})
    if kw:
        matched["dependency_words"] = kw
        reasons.append(f"task uses dependency-related wording: {kw}")

    installed = {norm_pkg(d.name) for d in env.dependencies}
    cap_hits: dict[str, list[str]] = {}
    for pkg, vocab in CAPABILITY_WORDS.items():
        if pkg not in installed or (pkg in TEST_RUNNERS and not is_test_task):
            continue
        hits = sorted({w for w in vocab if (" " in w and w in lower) or w in words})
        if hits:
            cap_hits[pkg] = hits
    if cap_hits:
        matched["capability_words"] = [f"{p}: {', '.join(h)}" for p, h in cap_hits.items()]
        reasons.append(f"task wording overlaps what installed dependencies provide: {cap_hits}")

    if reasons:
        return RiskAssessment("high", reasons, matched, sorted(imports))
    return RiskAssessment("low", ["no dependency names, third-party identifiers, dependency wording or dependency "
                                  "capability words in the task, and the project has tests: planner skipped; the "
                                  "generated code is still audited against installed packages"], matched, sorted(imports))
