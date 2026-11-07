"""Combined workflow (Track 1 x Track 2): installed-package source as evidence for API claims.

When an answer makes claims about a library that is installed in a selected workspace ("use pydantic's
@validator decorator", "zod's ZodString.nonempty() checks for empty strings"), VeriCode checks the named API
against the INSTALLED source with the same local verifiers used by the Pre-Flight gatekeeper:
  * Python: static AST over site-packages (existence, @deprecated / DeprecationWarning, migration messages)
  * TypeScript: TypeScript compiler API over node_modules (exports, members, @deprecated)
The resulting evidence is version-specific (it describes the installed version, not "the latest" one) and is
labelled origin=installed_source. It never produces a replacement value, so it can flag but never rewrite.
"""
from __future__ import annotations

import re
from pathlib import Path

from .claims import Claim
from .repo_intel import ProjectEnvironment, norm_pkg

DEPRECATION_WORDS = re.compile(r"\b(deprecated|obsolete|legacy|replaced by|superseded)\b", re.I)
REMOVAL_WORDS = re.compile(r"\b(removed|no longer (?:provides?|exists?|available|has|includes?|supports?)|dropped|does not (?:provide|exist|have)|doesn't (?:provide|exist|have))\b", re.I)
SYMBOL_PATTERNS = [
    re.compile(r"`@?([A-Za-z_][\w.]*)(?:\(\))?`"),            # `field_validator` / `BaseModel.dict()`
    re.compile(r"@([A-Za-z_][\w.]*)"),                        # @validator
    re.compile(r"\b([A-Za-z_][\w]*(?:\.[A-Za-z_]\w*)+)\(\)"),  # BaseModel.dict()
    re.compile(r"\b([A-Za-z_]\w*)\(\)"),                      # nonempty()
    re.compile(r"\b([A-Z][a-z]+[A-Z]\w*(?:\.\w+)?)\b"),        # CamelCase / ZodString.min
    re.compile(r"\b([a-z]+_[a-z_]+)\b"),                      # snake_case identifiers
    re.compile(r"\b(?:the\s+)?([A-Za-z_]\w*)\s+(?:decorator|function|method|class|helper|hook)\b"),  # "validator decorator"
    re.compile(r"\b(?:decorator|function|method|class)\s+([A-Za-z_]\w*)\b"),                         # "method dict"
]
_NOT_SYMBOLS = {"the", "this", "that", "a", "an", "new", "old", "main", "base", "custom", "deprecated", "current"}


def _import_name(dist_path: str | None, dist: str) -> str:
    if dist_path:
        tl = Path(dist_path) / "top_level.txt"
        if tl.exists():
            first = tl.read_text().split()
            if first:
                return first[0]
    return dist.replace("-", "_")


def candidate_symbols(text: str) -> list[str]:
    out: list[str] = []
    for pat in SYMBOL_PATTERNS:
        for m in pat.finditer(text):
            s = m.group(1).strip(".")
            if s and s not in out and len(s) >= 3 and s.lower() not in _NOT_SYMBOLS:
                out.append(s)
    return out[:8]


def mentioned_packages(c: Claim, env: ProjectEnvironment) -> list:
    words = {norm_pkg(w) for w in re.findall(r"[A-Za-z][\w\-.]+", c.claim)}
    return [d for d in env.dependencies if d.installed and norm_pkg(d.name) in words]


def check_claim(c: Claim, env: ProjectEnvironment) -> list[dict]:
    """Return evidence dicts: {title,url,domain,source_type,authority,excerpt,outcome,reason,method}."""
    out: list[dict] = []
    pkgs = mentioned_packages(c, env)
    if not pkgs:
        return out
    claims_removal = bool(REMOVAL_WORDS.search(c.claim))
    claims_deprecation = bool(DEPRECATION_WORDS.search(c.claim)) and not claims_removal
    for dep in pkgs:
        for sym in candidate_symbols(c.claim):
            if norm_pkg(sym) == norm_pkg(dep.name):
                continue
            info = _resolve(env, dep, sym)
            if info is None:
                continue
            found, deprecated, hint, location = info
            if not found and not hint:
                continue  # unknown symbol: absence is not evidence
            where = f"installed {dep.name} {dep.installed}" + (f" ({location})" if location else "")
            if found and deprecated:
                excerpt = f"In {where}, `{sym}` is marked deprecated: {deprecated}"
                if claims_removal:
                    outcome, reason = "contradict", "claim says the API was removed, but the installed version still provides it (deprecated)"
                elif claims_deprecation:
                    outcome, reason = "support", "installed source confirms the API is deprecated"
                else:
                    outcome, reason = "contradict", "claim presents a deprecated API as current; installed source marks it deprecated"
            elif found:
                excerpt = f"In {where}, `{sym}` exists and is not marked deprecated."
                outcome = "contradict" if (claims_deprecation or claims_removal) else "support"
                reason = ("claim says the API is deprecated/removed but the installed version provides it without deprecation"
                          if outcome == "contradict" else "installed source provides this API (version-specific evidence)")
            else:
                excerpt = f"In installed {dep.name} {dep.installed}, `{sym}` does not exist. {hint}"
                outcome = "support" if (claims_removal or claims_deprecation) else "contradict"
                reason = ("installed source confirms the API was removed/moved" if outcome == "support"
                          else "claim refers to an API that the installed version does not provide")
            out.append({"title": f"Installed source: {dep.name} {dep.installed}", "url": f"installed://{dep.name}@{dep.installed}/{location or sym}",
                        "domain": f"{dep.name}@{dep.installed}", "source_type": "installed_package_source (version-specific)",
                        "authority": 1.0, "excerpt": excerpt[:600], "outcome": outcome, "reason": reason, "method": "installed_source",
                        "symbol": sym, "package": dep.name, "version": dep.installed})
            break  # one decisive symbol per package
    return out


def _resolve(env: ProjectEnvironment, dep, sym: str):
    if dep.ecosystem == "python" and env.python_site_packages:
        from .pyinspect import PyResolver
        r = PyResolver(Path(env.python_site_packages))
        info = r.resolve(_import_name(dep.installed_path, dep.name), sym)
        return info.found, info.deprecated, info.migration_hint, info.location
    if dep.ecosystem == "node" and env.node_modules:
        from . import jsinspect
        if not jsinspect.ts_checker_available():
            return None
        name, _, member = sym.partition(".")
        r = jsinspect.ts_compiler_check(Path(env.root), dep.name, name, member)
        if r.get("error") and not r.get("resolved"):
            return None
        return bool(r.get("found")), r.get("deprecated"), None, r.get("location")
    return None
