"""Source authority: configurable trusted-domain registry + category rules + publisher/entity matching.

Authority describes WHO published a source, never whether the source supports a claim (that is decided by the
content checks in stale.py) and never how fresh it is. It is applied only to sources whose content passed the
relevance gate, so an unrelated page on an official domain cannot become "authoritative support".

Resolution order (first match wins), each with an explanation:
  1. suspected impersonation  - a trusted domain embedded in a different registrable domain
                                (python.org.example.net, docs-python.org) or a 1-edit typo of one (pyth0n.org)  -> 0.10
  2. user-preferred domains for this request                                                                    -> 0.95 primary
  3. category primary sources (Settings > authority_rules)                                                      -> 0.95 primary
  4. government / regulator / legislative publications                                                          -> 1.00 primary
  5. standards bodies                                                                                           -> 0.90 primary
  6. the claim's own publisher/entity (registrable label == a proper noun in the claim)                         -> 0.90 primary
  7. trusted registry classes (official software docs, package registries, research publishers)               -> 0.80-0.85
  8. news, encyclopedias                                                                                        -> 0.70 / 0.60 secondary
  9. community / user-generated                                                                                 -> 0.35 secondary
 10. unknown                                                                                                    -> 0.40 unknown
Domain matching is exact host or dot-bounded subdomain only ("evilpython.org" never matches "python.org").
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .config import settings

DEFAULT_TRUSTED_REGISTRY: dict[str, list[str]] = {
    "government": [".gov", ".gov.uk", ".gov.in", ".gov.au", ".gc.ca", ".gouv.fr", ".gob.es", ".go.jp", ".govt.nz", ".mil",
                   "europa.eu", "legislation.gov.uk", "eur-lex.europa.eu", "un.org", "who.int", "oecd.org"],
    "standards": ["w3.org", "whatwg.org", "ietf.org", "rfc-editor.org", "iso.org", "ecma-international.org", "unicode.org",
                  "ieee.org", "nist.gov"],
    "official_software_docs": ["python.org", "docs.python.org", "peps.python.org", "nodejs.org", "developer.mozilla.org", "react.dev",
                               "typescriptlang.org", "docs.pydantic.dev", "fastapi.tiangolo.com", "go.dev", "rust-lang.org",
                               "kubernetes.io", "docs.djangoproject.com", "djangoproject.com", "flask.palletsprojects.com",
                               "zod.dev", "vitest.dev", "vite.dev", "nextjs.org", "learn.microsoft.com", "developer.apple.com",
                               "developer.android.com", "docs.github.com", "docs.docker.com", "postgresql.org", "sqlite.org"],
    "package_registry": ["pypi.org", "npmjs.com", "registry.npmjs.org", "crates.io", "pkg.go.dev", "rubygems.org",
                         "packagist.org", "nuget.org", "github.com"],
    "research": ["doi.org", "nature.com", "science.org", "acm.org", "dl.acm.org", "pubmed.ncbi.nlm.nih.gov", "arxiv.org",
                 "sciencedirect.com", "springer.com", "thelancet.com", "nejm.org"],
    "news": ["reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com", "theverge.com", "techcrunch.com",
             "bloomberg.com", "ft.com", "wsj.com", "arstechnica.com", "theguardian.com", "cnbc.com"],
    "encyclopedia": ["wikipedia.org", "britannica.com"],
    "community": ["medium.com", "dev.to", "reddit.com", "quora.com", "stackoverflow.com", "stackexchange.com", "blogspot.com",
                  "wordpress.com", "substack.com", "hashnode.dev", "linkedin.com", "facebook.com", "x.com", "twitter.com",
                  "geeksforgeeks.org", "w3schools.com", "tutorialspoint.com", "youtube.com"],
}
CLASS_SCORE = {"government": (1.0, "primary"), "standards": (0.9, "primary"), "official_software_docs": (0.85, "primary"),
               "package_registry": (0.8, "primary"), "research": (0.85, "primary"), "news": (0.7, "secondary"),
               "encyclopedia": (0.6, "secondary"), "community": (0.35, "secondary")}
MULTI_PART_TLDS = {"co.uk", "gov.uk", "ac.uk", "org.uk", "com.au", "gov.au", "co.jp", "go.jp", "gov.in", "co.in", "com.br",
                   "gouv.fr", "gob.es", "govt.nz", "co.nz", "gc.ca"}
GENERIC_LABELS = {"www", "docs", "developer", "developers", "news", "blog", "help", "support", "about", "learn", "newsroom",
                  "investor", "investors", "api", "app", "en", "status", "community", "forum", "shop", "store"}


@dataclass
class Authority:
    score: float
    source_type: str
    tier: str  # primary | secondary | unknown | suspicious
    matched_rule: str
    explanation: str

    def to_dict(self) -> dict:
        return asdict(self)


def registry() -> dict[str, list[str]]:
    reg = {k: list(v) for k, v in DEFAULT_TRUSTED_REGISTRY.items()}
    for k, v in (getattr(settings, "trusted_registry", {}) or {}).items():
        reg.setdefault(k, [])
        reg[k] = sorted(set(reg[k]) | {d.lower() for d in v})
    return reg


def host_matches(host: str, pattern: str) -> bool:
    """Exact host or dot-bounded subdomain; patterns starting with '.' are suffix rules (e.g. '.gov')."""
    host, pattern = host.lower().rstrip("."), pattern.lower().removeprefix("www.")
    if pattern.startswith("."):
        return host.endswith(pattern) and len(host) > len(pattern)
    return host == pattern or host.endswith("." + pattern)


def registrable(host: str) -> str:
    parts = host.lower().split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in MULTI_PART_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _edit1(a: str, b: str) -> bool:
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, l = (a, b) if len(a) < len(b) else (b, a)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def impersonation(host: str, trusted: list[str]) -> str | None:
    reg = registrable(host)
    for t in trusted:
        if t.startswith("."):
            continue
        treg = registrable(t)
        if host_matches(host, t) or reg == treg:
            return None
    for t in trusted:
        if t.startswith(".") or "." not in t:
            continue
        treg = registrable(t)
        tname = treg.split(".")[0]
        if f".{treg}." in f".{host}." and reg != treg:
            return f"contains trusted domain '{treg}' but is registered under '{reg}'"
        if reg.replace("-", ".") .endswith(treg) and reg != treg and "-" in reg:
            return f"hyphenated look-alike of '{treg}'"
        if len(tname) >= 5 and _edit1(reg.split(".")[0], tname) and reg.split(".", 1)[-1] == treg.split(".", 1)[-1]:
            return f"one-character variation of '{treg}'"
    return None


def proper_nouns(claim_text: str) -> set[str]:
    words = re.findall(r"\b[A-Z][A-Za-z0-9]+\b", claim_text or "")
    out = {w.lower() for i, w in enumerate(words) if len(w) >= 3}
    return out


# Product names that are published by a differently named organisation (claim mentions the product, the official
# site carries the publisher's name). Small and explicit on purpose; extend via code review, not heuristics.
ENTITY_ALIASES = {"chatgpt": {"openai"}, "gpt": {"openai"}, "dalle": {"openai"}, "claude": {"anthropic"},
                  "gemini": {"google"}, "chrome": {"google"}, "android": {"google"}, "copilot": {"github", "microsoft"},
                  "windows": {"microsoft"}, "azure": {"microsoft"}, "iphone": {"apple"}, "macos": {"apple"},
                  "llama": {"meta"}, "aws": {"amazon"}, "cpython": {"python"}}


def assess(url: str, preferred: list[str] | None = None, category: str | None = None, claim_text: str = "",
           claim_terms: list[str] | None = None) -> Authority:
    from .tavily import domain_of
    host = domain_of(url)
    if not host:
        return Authority(0.0, "invalid_url", "unknown", "none", "URL has no host")
    reg = registry()
    all_trusted = [d for k, v in reg.items() if k != "community" for d in v] + list(preferred or []) + \
        [d for ds in settings.authority_rules.values() for d in ds]
    imp = impersonation(host, all_trusted)
    if imp:
        return Authority(0.1, "suspected_impersonation", "suspicious", "impersonation", f"{host}: {imp}")
    for p in preferred or []:
        if host_matches(host, p):
            return Authority(0.95, "preferred_source", "primary", f"preferred:{p}", f"{host} matches user-preferred domain {p}")
    if category:
        for p in settings.authority_rules.get(category, []):
            if host_matches(host, p):
                return Authority(0.95, f"primary_source_for_{category}", "primary", f"category:{category}:{p}",
                                 f"{host} is a configured primary source for {category} claims ({p})")
    for cls in ("government", "standards"):
        for p in reg.get(cls, []):
            if host_matches(host, p):
                s, tier = CLASS_SCORE[cls]
                return Authority(s, cls, tier, f"registry:{cls}:{p}", f"{host} matches {cls} registry entry {p}")
    for p in reg.get("community", []):
        if host_matches(host, p):
            return Authority(0.35, "community/blog (secondary)", "secondary", f"registry:community:{p}",
                             f"{host} is user-generated/community content ({p})")
    entities = proper_nouns(claim_text) | {t.lower() for t in (claim_terms or []) if t[:1].isupper()}
    entities |= {a for e in list(entities) for a in ENTITY_ALIASES.get(e, ())}
    label = registrable(host).split(".")[0].replace("-", "")
    if label in entities and label not in GENERIC_LABELS and len(label) >= 4:
        return Authority(0.9, "official_entity_site", "primary", f"entity:{label}",
                         f"registrable domain {registrable(host)} matches the entity '{label}' named in the claim")
    for cls in ("official_software_docs", "package_registry", "research", "news", "encyclopedia"):
        for p in reg.get(cls, []):
            if host_matches(host, p):
                s, tier = CLASS_SCORE[cls]
                return Authority(s, cls if tier == "primary" else f"{cls} (secondary)", tier, f"registry:{cls}:{p}",
                                 f"{host} matches {cls} registry entry {p}")
    return Authority(0.4, "unknown", "unknown", "none",
                     f"{host} is not in any trusted registry and does not match an entity named in the claim")
