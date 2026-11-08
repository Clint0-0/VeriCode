"""Modules C+F - Local dependency truth engine orchestration and deterministic risk engine.

Separate values per finding (never collapsed): api_compatibility, evidence_freshness,
verification_confidence, risk_score. risk_score is an additive explainable index (0-100), NOT a probability.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from packaging.version import InvalidVersion, Version

from . import jsinspect, memory
from .pyinspect import PyResolver, SymbolInfo, check_arguments, runtime_introspect
from .repo_intel import ProjectEnvironment, norm_pkg
from .skeleton import PlannedAPI, PlannedPackage, Skeleton
from .tavily import TavilyClient, domain_of

RISK_WEIGHTS = {
    "not_found": 60, "rejected_argument": 50, "unsupported_argument": 40, "deprecated": 30,
    "package_missing": 60, "assumed_major_mismatch": 20, "uncertain_argument": 8,
    "unverifiable": 25, "live_conflict": 15,
}


@dataclass
class APIFinding:
    package: str
    ecosystem: str
    planned_api: str
    api_type: str
    arguments: list[str]
    installed_version: str | None
    assumed_version: str | None
    status: str = "NOT_CHECKED"
    api_compatibility: str = "unknown"  # compatible | incompatible | deprecated | unknown
    verification_confidence: str = "low"  # high | medium | low
    evidence_freshness: float | None = None
    risk_score: int = 0
    risk_factors: list[dict] = field(default_factory=list)
    explanation: str = ""
    suggested_correction: str | None = None
    verification_method: list[str] = field(default_factory=list)
    local: dict | None = None
    argument_checks: list[dict] = field(default_factory=list)
    live: dict | None = None
    memory_rule: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def add_risk(self, factor: str, detail: str) -> None:
        w = RISK_WEIGHTS[factor]
        self.risk_factors.append({"factor": factor, "weight": w, "detail": detail})
        self.risk_score = min(100, self.risk_score + w)


def _major(v: str | None) -> int | None:
    if not v:
        return None
    m = re.match(r"\D*(\d+)", v)
    return int(m.group(1)) if m else None


def _doc_domains(dep_path: str | None) -> list[str]:
    """Documentation/homepage domains declared in installed package metadata (Project-URL, Home-page)."""
    if not dep_path:
        return []
    p = Path(dep_path)
    meta = p / "METADATA" if (p / "METADATA").exists() else p / "package.json"
    doms: list[str] = []
    try:
        text = meta.read_text(errors="ignore")
    except OSError:
        return []
    for url in re.findall(r"https?://[^\s\"',]+", text[:20000]):
        d = domain_of(url)
        if d and d not in doms and d not in ("github.com", "pypi.org", "img.shields.io", "badge.fury.io", "codecov.io", "opensource.org"):
            doms.append(d)
    return doms[:3]


def verify_planned_api(env: ProjectEnvironment, pkg: PlannedPackage, api: PlannedAPI) -> APIFinding:
    dep = env.dep(pkg.package)
    installed = dep.installed if dep else None
    f = APIFinding(package=pkg.package, ecosystem=pkg.ecosystem, planned_api=f"{api.import_path}.{api.name}" if pkg.ecosystem == "python" else f"{api.import_path}:{api.name}",
                   api_type=api.type, arguments=api.arguments, installed_version=installed,
                   assumed_version=pkg.assumed_version)
    # memory: verified rules for this package+version
    rule = memory.find_rule(pkg.package, installed, api.name)
    if rule:
        f.memory_rule = rule
    if dep is None or not installed:
        f.status, f.api_compatibility = "NOT_FOUND", "incompatible"
        why = "not declared or installed in the project" if dep is None else f"declared ({dep.declared}) but not installed ({dep.status})"
        f.add_risk("package_missing", f"package {pkg.package} {why}")
        f.explanation = f"Package {pkg.package} is {why}."
        f.verification_method.append("manifest+installed-metadata")
        return f

    am, im = _major(pkg.assumed_version), _major(installed)
    if am is not None and im is not None and am != im:
        f.add_risk("assumed_major_mismatch", f"planner assumed {pkg.assumed_version}, installed is {installed}")

    if pkg.ecosystem == "python":
        if not env.python_site_packages:
            f.status = "UNCERTAIN"
            f.add_risk("unverifiable", "no virtualenv site-packages found")
            f.explanation = "Installed environment not accessible; cannot verify statically."
            return f
        r = PyResolver(Path(env.python_site_packages))
        info: SymbolInfo = r.resolve(api.import_path, api.name if api.type != "module" else "")
        f.verification_method.append("static_ast(installed source)")
        if not info.found and not info.migration_hint and api.type != "module" and "." in api.import_path:
            # Planners often write a class into the import path ("pydantic.BaseModel" + "model_dump"). Retry with
            # trailing segments treated as attributes of a shorter module path before declaring NOT_FOUND.
            parts = api.import_path.split(".")
            for i in range(len(parts) - 1, 0, -1):
                alt = r.resolve(".".join(parts[:i]), ".".join(parts[i:] + [api.name]))
                if alt.found or alt.migration_hint:
                    alt.resolution_path = [f"import path '{api.import_path}' re-read as module '{'.'.join(parts[:i])}' "
                                           f"+ attribute '{'.'.join(parts[i:] + [api.name])}'"] + list(alt.resolution_path)
                    info = alt
                    break
        if not info.found and not info.migration_hint:
            py = Path(env.root) / ".venv" / "bin" / "python"
            if py.exists():
                rt = runtime_introspect(py, api.import_path, api.name)
                f.verification_method.append("runtime_isolated(subprocess -I, timeout)")
                if rt.get("found"):
                    info.found, info.method = True, "runtime_isolated"
                    info.params = [p for p in (rt.get("params") or [])]
                    info.accepts_var_kwargs = any("VAR_KEYWORD" in p.get("kind", "") for p in info.params)
                    info.note = "resolved at runtime only (dynamic attribute)"
        f.local = info.to_dict()
    else:
        if not env.node_modules:
            f.status = "UNCERTAIN"
            f.add_risk("unverifiable", "node_modules not present")
            f.explanation = "node_modules not installed; cannot verify exports."
            return f
        if jsinspect.ts_checker_available():
            return _apply_rule(_verify_ts(env, pkg, api, f))
        info = jsinspect.resolve(Path(env.node_modules), api.import_path, api.name if api.type != "module" else "")
        f.verification_method.append(info.method)
        f.local = info.to_dict()

    if not info.found:
        if info.method == "unverifiable":
            f.status = "UNCERTAIN"
            f.add_risk("unverifiable", info.note or "no declarations")
            f.explanation = info.note or "Could not verify."
        else:
            f.status, f.api_compatibility, f.verification_confidence = "NOT_FOUND", "incompatible", "high"
            f.add_risk("not_found", info.note or f"{api.name} not exported by installed {pkg.package} {installed}")
            f.explanation = f"`{api.name}` does not exist in installed {pkg.package} {installed}. " + (info.note or "")
            if info.migration_hint:
                f.suggested_correction = info.migration_hint
        return _apply_rule(f)

    f.argument_checks = check_arguments(info, api.arguments) if pkg.ecosystem == "python" else _js_args(info, api.arguments)
    problems = []
    for a in f.argument_checks:
        if a["status"] == "rejected":
            f.add_risk("rejected_argument", f"`{a['argument']}`: {a['detail']}")
            problems.append(f"argument `{a['argument']}` is rejected by installed code: {a['detail']}")
        elif a["status"] == "unsupported":
            f.add_risk("unsupported_argument", f"`{a['argument']}` not in signature")
            problems.append(f"argument `{a['argument']}` is not accepted")
        elif a["status"] == "uncertain":
            f.add_risk("uncertain_argument", f"`{a['argument']}` only matched by **kwargs")
    if info.deprecated:
        f.add_risk("deprecated", info.deprecated)
    if problems:
        f.status, f.api_compatibility, f.verification_confidence = "INCOMPATIBLE", "incompatible", "high"
        f.explanation = "; ".join(problems)
        f.suggested_correction = "; ".join(a["detail"] for a in f.argument_checks if a["status"] == "rejected") or None
    elif info.deprecated:
        f.status, f.api_compatibility, f.verification_confidence = "DEPRECATED", "deprecated", "high"
        f.explanation = f"Deprecated in installed {pkg.package} {installed}: {info.deprecated}"
        f.suggested_correction = info.deprecated
    elif any(x["factor"] == "assumed_major_mismatch" for x in f.risk_factors):
        f.status, f.api_compatibility = "STALE", "compatible"
        f.verification_confidence = "medium"
        f.explanation = f"API exists, but the plan was based on {pkg.package} {pkg.assumed_version} while {installed} is installed; behaviour may differ."
    else:
        f.status, f.api_compatibility = "VERIFIED_LOCAL", "compatible"
        uncertain = any(a["status"] == "uncertain" for a in f.argument_checks)
        f.verification_confidence = "medium" if uncertain or info.note else "high"
        f.explanation = f"Found at {info.location}" + (f" ({info.note})" if info.note else "")
    return _apply_rule(f)


TS_ARITY = {2554, 2555, 2556, 2575}
TS_TYPE = {2345, 2322, 2769, 2559, 2353}


def _verify_ts(env: ProjectEnvironment, pkg: PlannedPackage, api: PlannedAPI, f: APIFinding) -> APIFinding:
    """TypeScript compiler-API verification: module resolution (export maps, types), named/default exports,
    class/interface/namespace members, signatures (required/optional/rest, generics) and a real type-check
    of the planned call when the planner supplied TypeScript argument expressions."""
    parts = api.name.split(".", 1) if api.type != "module" else ["", ""]
    name, member = parts[0], (parts[1] if len(parts) > 1 else "")
    # no argument expressions planned -> existence/signature/deprecation only (a zero-argument call is not implied)
    args = (api.arguments or None) if api.type in ("function", "method", "class", "decorator") else None
    r = jsinspect.ts_compiler_check(Path(env.root), api.import_path, name, member, args)
    f.verification_method.append("typescript_compiler_api")
    f.local = {"location": r.get("location"), "resolved_file": r.get("resolved_file"), "package": r.get("package"),
               "export_kind": r.get("export_kind"), "kind": r.get("kind"), "signatures": r.get("signatures", []),
               "construct_signatures": r.get("construct_signatures", []), "deprecated": r.get("deprecated"),
               "call_check": r.get("call_check"), "similar_exports": r.get("similar_exports"), "error": r.get("error"),
               "method": "typescript_compiler_api"}
    if r.get("error") and r.get("resolved") and r.get("member_found") is not False and not r.get("found"):
        f.status = "UNCERTAIN"
        f.add_risk("unverifiable", r["error"])
        f.explanation = f"TypeScript check could not complete: {r['error']}"
        return f
    if not r.get("resolved"):
        f.status, f.api_compatibility, f.verification_confidence = "NOT_FOUND", "incompatible", "high"
        f.add_risk("not_found", r.get("error") or "module not resolvable")
        f.explanation = r.get("error") or f"module {api.import_path} cannot be resolved"
        return f
    if not r.get("found"):
        f.status, f.api_compatibility, f.verification_confidence = "NOT_FOUND", "incompatible", "high"
        what = f"{name}.{member}" if member else name
        why = r.get("error") or f"`{what}` is not exported by {api.import_path} {f.installed_version}"
        f.add_risk("not_found", why)
        f.explanation = why
        if r.get("similar_exports"):
            f.suggested_correction = "similar exports: " + ", ".join(r["similar_exports"])
        return f
    cc = r.get("call_check") or {}
    diags = cc.get("diagnostics") or []
    # identifiers the planner used inside argument expressions (its own variables) are unknowable here: those
    # diagnostics make the argument check uncertain, never INCOMPATIBLE
    unresolved = [d for d in diags if d["code"] in (2304, 2552, 2448)]
    diags = [d for d in diags if d not in unresolved]
    sigs = r.get("signatures") or r.get("construct_signatures") or []
    f.argument_checks = []
    if args is not None and cc:
        for d in unresolved:
            f.argument_checks.append({"argument": cc.get("source", ""), "status": "uncertain",
                                      "detail": f"TS{d['code']}: {d['message']} (planner-side identifier; not checkable)"})
        if not diags and not unresolved:
            f.argument_checks.append({"argument": cc.get("source", ""), "status": "supported", "detail": "call type-checks against installed declarations"})
        for d in diags:
            kind = "rejected" if d["code"] in TS_ARITY else "unsupported" if d["code"] in TS_TYPE else "unsupported"
            f.argument_checks.append({"argument": cc.get("source", ""), "status": kind, "detail": f"TS{d['code']}: {d['message']}"})
            f.add_risk("rejected_argument" if d["code"] in TS_ARITY else "unsupported_argument", f"TS{d['code']}: {d['message']}")
    if r.get("deprecated"):
        f.add_risk("deprecated", r["deprecated"])
    if diags:
        f.status, f.api_compatibility, f.verification_confidence = "INCOMPATIBLE", "incompatible", "high"
        f.explanation = "Planned call does not type-check against installed declarations: " + "; ".join(f"TS{d['code']}: {d['message']}" for d in diags)
        if sigs:
            f.suggested_correction = "installed signature: " + " | ".join(s["text"] for s in sigs[:3])
    elif r.get("deprecated"):
        f.status, f.api_compatibility, f.verification_confidence = "DEPRECATED", "deprecated", "high"
        f.explanation = f"Marked @deprecated in installed {f.package} {f.installed_version}: {r['deprecated']}"
        f.suggested_correction = r["deprecated"]
    elif any(x["factor"] == "assumed_major_mismatch" for x in f.risk_factors):
        f.status, f.api_compatibility, f.verification_confidence = "STALE", "compatible", "medium"
        f.explanation = f"Exists at {r.get('location')}, but the plan targeted {f.package} {f.assumed_version} while {f.installed_version} is installed."
    else:
        f.status, f.api_compatibility = "VERIFIED_LOCAL", "compatible"
        f.verification_confidence = "high" if (args is not None and cc and not unresolved) else "medium"
        f.explanation = f"Found at {r.get('location')}" + (
            "; existence and signature only (no call to type-check)" if not (args is not None and cc)
            else "; planned call type-checks apart from planner-side identifiers" if unresolved else "; planned call type-checks")
    return f


def _js_args(info, args: list[str]) -> list[dict]:
    if not info.params:
        return [{"argument": a, "status": "uncertain", "detail": "no parameter info in declaration"} for a in args]
    names = {p["name"] for p in info.params}
    has_rest = any(p.get("kind") == "rest" for p in info.params)
    out = []
    for a in args:
        if a in names:
            out.append({"argument": a, "status": "supported", "detail": "present in declaration"})
        else:
            out.append({"argument": a, "status": "uncertain" if has_rest or len(info.params) else "unsupported",
                        "detail": "positional/object argument names are not checked by name in TS declarations"})
    return out


def _apply_rule(f: APIFinding) -> APIFinding:
    if f.memory_rule and not f.suggested_correction:
        f.suggested_correction = f.memory_rule["correction"]
        f.verification_method.append("project_memory(verified rule)")
    return f


def live_verify(finding: APIFinding, env: ProjectEnvironment, client: TavilyClient) -> None:
    """Search official docs for version-specific evidence about a risky finding."""
    dep = env.dep(finding.package)
    domains = _doc_domains(dep.installed_path if dep else None)
    name = finding.planned_api.split(".")[-1].split(":")[-1]
    ver = finding.installed_version or ""
    q = f"{finding.package} {ver} {name} " + ("deprecated migration" if finding.status in ("DEPRECATED", "NOT_FOUND", "INCOMPATIBLE") else "API reference")
    out = client.search(q, include_domains=domains or None, max_results=4)
    finding.verification_method.append("tavily_live_search")
    if not out.ok:
        finding.live = {"status": out.status, "detail": out.detail, "query": q, "domains": domains, "sources": []}
        return
    sources = []
    for r in out.results:
        text = r.content or ""
        idx = text.find(name)
        excerpt = text[max(0, idx - 200): idx + 300] if idx >= 0 else text[:300]
        sources.append({"title": r.title, "url": r.url, "domain": domain_of(r.url), "published_date": r.published_date,
                        "excerpt": excerpt, "mentions_api": idx >= 0, "official": domain_of(r.url) in domains})
    finding.live = {"status": out.status, "query": q, "domains": domains, "retrieved_at": out.retrieved_at,
                    "cached": out.cached, "sources": sources}
    relevant = [s for s in sources if s["mentions_api"]]
    if finding.status in ("UNCERTAIN", "STALE") and relevant and any(s["official"] for s in relevant):
        finding.status = "VERIFIED_LIVE"
        finding.verification_confidence = "medium"
        finding.explanation += " Official documentation mentions this API (live evidence)."


def _task_local_identifier(env: ProjectEnvironment, pkg: PlannedPackage, api: PlannedAPI, f: APIFinding, task: str) -> bool:
    """A planner sometimes lists an identifier the task itself asks to create (e.g. 'RegistrationSchema.parse' under
    zod). If the top-level name is not a package export AND appears in the task text, it is project-local code, not a
    hallucinated package API. Hallucinated exports that the task does not mention stay NOT_FOUND."""
    if f.status != "NOT_FOUND" or not task:
        return False
    top = api.name.split(".")[0]
    if not top or not re.search(rf"\b{re.escape(top)}\b", task):
        return False
    probe = verify_planned_api(env, pkg, PlannedAPI(import_path=api.import_path, name=top, type="class", arguments=[]))
    return probe.status == "NOT_FOUND"


def verify_skeleton(env: ProjectEnvironment, sk: Skeleton, client: TavilyClient | None = None, live: bool = True,
                    task: str = "") -> list[APIFinding]:
    findings = []
    for pkg in sk.packages:
        for api in pkg.planned_apis:
            f = verify_planned_api(env, pkg, api)
            if _task_local_identifier(env, pkg, api, f, task):
                f.status = "UNCERTAIN"
                f.verification_confidence = "medium"
                f.explanation = (f"'{api.name.split('.')[0]}' is not exported by {pkg.package} but is named in the task as "
                                 "code to write; treated as a project-local identifier, not a package API.")
                findings.append(f)
                continue
            if live and client is not None and (f.status not in ("VERIFIED_LOCAL",) or api.version_sensitive):
                live_verify(f, env, client)
            findings.append(f)
    return findings


def version_satisfies(installed: str, spec: str) -> bool | None:
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    try:
        return Version(installed) in SpecifierSet(spec)
    except (InvalidSpecifier, InvalidVersion):
        return None
