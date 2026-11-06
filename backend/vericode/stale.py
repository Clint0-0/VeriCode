"""Module E steps 2-6 - evidence retrieval, claim verification, freshness + confidence scoring, correction.

Verification is deterministic and explainable: a source must be RELEVANT (subject-term overlap) and must
contain the claim's concrete values (support) or conflicting values of the same type (contradiction).
Topic mentions alone never verify a claim.

Scores (kept separate):
  Evidence Freshness = 100 * 2^(-age_days / half_life[category])   (from the source's published/updated
                       date only; unknown when the source has no date - retrieval time is never used)
  Verification Confidence (0-100 evidence-strength index, NOT a probability) =
       35*authority + 25*relevance + 15*specificity + 15*corroboration + 10*date_known - 30*conflict
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import db
from .claims import Claim, extract_claims, extract_values
from .config import ROOT, settings
from .security import SecurityError, check_public_url, redact
from .tavily import SearchOutcome, TavilyClient, TavilyResult, domain_of

CATEGORY_QUERY_HINT = {
    "pricing": "official pricing", "leadership": "official announcement", "law_regulation": "official government",
    "software_version": "official release notes", "api_documentation": "official documentation",
    "release_date": "official announcement", "product_spec": "official specifications", "deadline": "official",
    "current_events": "news", "other_volatile": "official",
}
NEWS = {"reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com", "theverge.com", "techcrunch.com",
        "bloomberg.com", "ft.com", "wsj.com", "arstechnica.com", "theguardian.com", "cnbc.com"}
LOW = {"medium.com", "dev.to", "reddit.com", "quora.com", "stackoverflow.com", "blogspot.com", "wordpress.com",
       "substack.com", "hashnode.dev", "linkedin.com", "facebook.com", "x.com", "twitter.com"}
OFFICIAL_HINTS = ("docs.", "developer.", "developers.", "learn.", "support.", "help.", "newsroom.", "news.", "investor.", "about.", "blog.")


def authority(url: str, preferred: list[str] | None = None) -> tuple[float, str]:
    d = domain_of(url)
    preferred = [p.lower().removeprefix("www.") for p in (preferred or [])]
    if any(d == p or d.endswith("." + p) for p in preferred):
        return 0.95, "preferred_source"
    if re.search(r"(\.gov(\.[a-z]{2})?|\.gouv\.[a-z]{2}|\.gob\.[a-z]{2}|\.mil|europa\.eu|legislation\.gov\.uk|\.govt\.nz|gc\.ca)$", d):
        return 1.0, "government"
    if any(d == l or d.endswith("." + l) for l in LOW):
        return 0.35, "community/blog"
    if d.endswith("wikipedia.org"):
        return 0.6, "encyclopedia"
    if d in NEWS or any(d.endswith("." + n) for n in NEWS):
        return 0.7, "news"
    if d in ("pypi.org", "npmjs.com", "github.com", "registry.npmjs.org"):
        return 0.8, "package_registry/repository"
    if d.startswith(OFFICIAL_HINTS) or d.endswith((".org", ".io", ".dev")) and d.count(".") <= 2:
        return 0.85, "official_documentation/organization"
    return 0.55, "general_web"


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S GMT", "%B %d, %Y", "%b. %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def freshness(published: str | None, category: str, now: datetime | None = None) -> tuple[float | None, float | None]:
    d = parse_date(published)
    if not d:
        return None, None
    now = now or datetime.now(timezone.utc)
    age = max(0.0, (now - d).total_seconds() / 86400)
    hl = settings.half_lives.get(category, 180)
    return round(100 * 2 ** (-age / hl), 1), round(age, 1)


# ----------------------------------------------------------------------------- sources
class FixtureSearch:
    """Offline, deterministic evidence provider for tests/demos. Results are labelled origin=fixture."""

    def __init__(self, path: Path):
        self.data = json.loads(path.read_text())
        self.calls = 0
        self.api_key = "fixture"

    def search(self, query: str, include_domains=None, max_results: int = 5, **kw) -> SearchOutcome:
        self.calls += 1
        if self.data.get("simulate_failure"):
            return SearchOutcome(ok=False, status=self.data["simulate_failure"], query=query, detail="fixture-simulated failure")
        q = set(re.findall(r"[a-z0-9.\-]+", query.lower()))
        scored = []
        for s in self.data["sources"]:
            kws = set(s.get("keywords", []))
            hit = len(q & kws)
            if hit >= s.get("min_match", 2):
                scored.append((hit, s))
        scored.sort(key=lambda x: -x[0])
        res = [TavilyResult(title=s["title"], url=s["url"], content=s["content"], published_date=s.get("published_date"))
               for _, s in scored[:max_results]]
        return SearchOutcome(ok=True, status="ok" if res else "no_results", query=query, results=res,
                             retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def extract(self, urls):
        return {}


def fetch_url(url: str, timeout: float = 15) -> tuple[str, str, str | None]:
    """Fetch a user-supplied URL with SSRF protection (public hosts only, no redirects to private IPs)."""
    check_public_url(url)
    with httpx.Client(timeout=timeout, follow_redirects=False, headers={"User-Agent": "VeriCode/1.0 (evidence fetcher)"}) as c:
        r = c.get(url)
        hops = 0
        while r.is_redirect and hops < 3:
            nxt = str(r.next_request.url) if r.next_request else None
            if not nxt:
                break
            check_public_url(nxt)
            r = c.get(nxt)
            hops += 1
        r.raise_for_status()
        body = r.text[:500_000]
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    pub = re.search(r'(?:article:published_time|article:modified_time|datePublished|dateModified)"?\s*(?:content=|:)\s*"([^"]+)"', body)
    text = re.sub(r"<(script|style|nav|footer)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text)
    return (html.unescape(title.group(1).strip()) if title else url), text, (pub.group(1) if pub else None)


# ----------------------------------------------------------------------------- comparison
def best_excerpt(text: str, terms: list[str], values: dict, width: int = 2) -> tuple[str, float]:
    sents = re.split(r"(?<=[.!?])\s+", text)
    if not sents:
        return "", 0.0
    best, best_score = "", -1.0
    flat_vals = [v.split()[-1] for vs in values.values() for v in vs]
    for i in range(len(sents)):
        win = " ".join(sents[i: i + width])
        lw = win.lower()
        score = sum(1 for t in terms if t in lw) + 0.5 * sum(1 for v in flat_vals if v.lower() in lw)
        if score > best_score:
            best, best_score = win, score
    lw = best.lower()
    overlap = sum(1 for t in terms if t in lw) / max(1, len(terms))
    return best[:600], round(overlap, 2)


def _vkey(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def _version_match(cv: str, evs: list[str]) -> bool:
    return any(e == cv or e.startswith(cv + ".") for e in evs)


def compare(claim: Claim, excerpt: str) -> tuple[str, str, str | None]:
    """Return (outcome, reason, replacement) with outcome in support|contradict|neutral."""
    ev = extract_values(excerpt)
    cv = claim.values
    latest_claim = bool(re.search(r"\b(latest|newest|most recent|current)\b", claim.claim, re.I))
    if "version" in cv:
        evs = ev.get("version", [])
        c = cv["version"][0]
        if latest_claim and evs:
            top = max(evs, key=_vkey)
            if _vkey(top)[:2] > _vkey(c)[:2]:
                return "contradict", f"source shows newer version {top} than claimed latest {c}", ".".join(top.split(".")[:2])
            if _version_match(c, evs):
                return "support", f"source's highest version {top} matches claimed {c}", None
        if evs and _version_match(c, evs):
            return "support", f"source mentions version {c}", None
        return "neutral", "claimed version not found in source", None
    if "money" in cv:
        evm = ev.get("money", [])
        if any(m in evm for m in cv["money"]):
            return "support", f"source states {cv['money'][0]}", None
        same_cur = [m for m in evm if m.split()[0] == cv["money"][0].split()[0]]
        if same_cur:
            return "contradict", f"source states {same_cur[0]} instead of {cv['money'][0]}", same_cur[0]
        return "neutral", "no price found in source", None
    if "name" in cv and claim.category == "leadership":
        names = ev.get("name", [])
        if any(n in excerpt for n in cv["name"]):
            return "support", f"source names {cv['name'][0]}", None
        if names:
            return "contradict", f"source names {names[0]} for this role", names[0]
        return "neutral", "no person named in source excerpt", None
    for key in ("percent", "year"):
        if key in cv:
            evv = ev.get(key, [])
            if any(v in evv for v in cv[key]):
                return "support", f"source states {cv[key][0]}", None
            if evv and key == "percent":
                return "contradict", f"source states {evv[0]}% instead of {cv[key][0]}%", evv[0] + "%"
            return "neutral", f"claimed {key} not found in source", None
    return "neutral", "claim has no concrete value; source relevance alone does not verify it", None


@dataclass
class EvidenceRecord:
    claim_id: str
    original_claim: str
    title: str
    url: str
    domain: str
    source_type: str
    authority: float
    retrieved_at: str
    published_date: str | None
    excerpt: str
    relevance: float
    relevance_explanation: str
    outcome: str
    origin: str  # live_tavily | user_url | fixture
    freshness: float | None = None
    age_days: float | None = None
    replacement: str | None = None


@dataclass
class ClaimReport:
    claim: dict
    status: str
    freshness: float | None
    freshness_note: str
    confidence: float | None
    confidence_breakdown: dict
    explanation: str
    evidence: list[dict] = field(default_factory=list)
    correction: str | None = None
    query: str | None = None
    search_status: str | None = None


def build_query(c: Claim) -> str:
    core = re.sub(r"\s+", " ", c.claim)[:200]
    return f"{core} {CATEGORY_QUERY_HINT.get(c.category, '')}".strip()


def verify_claim(c: Claim, search, user_sources: list[tuple[str, str, str | None]], preferred: list[str],
                 now: datetime | None = None, origin: str = "live_tavily") -> ClaimReport:
    if not c.requires_verification:
        return ClaimReport(c.to_dict(), "NOT_APPLICABLE", None, "not assessed (stable claim)", None, {},
                           f"Not time-sensitive: {c.reason}.")
    q = build_query(c)
    out = search.search(q, include_domains=preferred or None, max_results=5)
    retrieved = out.retrieved_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    raw: list[tuple[str, str, str, str | None, str]] = [(t, u, txt, pub, "user_url") for (u, t, txt, pub) in user_sources]
    if out.ok:
        full = {}
        if hasattr(search, "extract") and origin == "live_tavily":
            tops = [r.url for r in out.results[:2]]
            full = search.extract(tops)  # inspect actual pages, not just snippets
        for r in out.results:
            raw.append((r.title, r.url, full.get(r.url) or r.content, r.published_date, origin))
    records: list[EvidenceRecord] = []
    for title, url, text, pub, org in raw:
        excerpt, rel = best_excerpt(text, c.subject_terms, c.values)
        auth, stype = authority(url, preferred)
        outcome, reason, repl = compare(c, excerpt) if rel >= 0.34 else ("irrelevant", "source does not discuss the claim's subject", None)
        fr, age = freshness(pub, c.category, now)
        records.append(EvidenceRecord(c.claim_id, c.claim, title, url, domain_of(url), stype, auth, retrieved, pub, excerpt, rel,
                                      f"{int(rel * 100)}% subject-term overlap; {reason}", outcome, org, fr, age, repl))
    sup = [r for r in records if r.outcome == "support"]
    con = [r for r in records if r.outcome == "contradict"]
    decisive: list[EvidenceRecord] = []
    correction = None
    if sup and con:
        sd = [parse_date(r.published_date) for r in sup]
        cd = [parse_date(r.published_date) for r in con]
        if all(sd) and all(cd) and min(cd) > max(sd) and max(r.authority for r in con) >= 0.5:  # newer, non-community source
            status, decisive = "CONTRADICTED", con
            expl = "Newer authoritative evidence contradicts the claim; older sources supported it at the time."
        else:
            status, decisive = "CONFLICTING_EVIDENCE", sup + con
            expl = "Sources disagree; see evidence for both sides."
    elif con:
        status, decisive, expl = "CONTRADICTED", con, "Relevant evidence contradicts the claim."
    elif sup:
        decisive = sup
        best_f = max((r.freshness for r in sup if r.freshness is not None), default=None)
        if c.temporal and not c.past_event and best_f is not None and best_f < 25:
            status, expl = "POTENTIALLY_STALE", "Supporting evidence is old relative to how often this kind of fact changes."
        else:
            status, expl = "CURRENT_SUPPORTED", "Relevant evidence supports the claim."
            if c.past_event:
                expl += " (Past-event claim: evidence age does not make it stale.)"
            if best_f is None:
                expl += " Source dates unknown, so currency cannot be confirmed by date."
    else:
        status = "UNVERIFIED"
        if not out.ok and not user_sources:
            expl = f"Live verification could not be performed ({out.status}: {out.detail})."
        elif not records:
            expl = "No sources found for this claim."
        else:
            expl = "Sources were found but none contained evidence that supports or contradicts the claim's specific values."
    if decisive:
        expl += " " + "; ".join(sorted({r.relevance_explanation.split('; ', 1)[1] for r in decisive}))[:400]
    if status == "CONTRADICTED" and decisive and all((r.freshness or 0) < 25 for r in decisive):
        expl += " Note: the contradicting evidence is itself old for this category; an even newer value may exist."
    if status == "CONTRADICTED":
        repls = [r.replacement for r in decisive if r.replacement]
        correction = repls[0] if repls else None
    fr_vals = [r.freshness for r in decisive if r.freshness is not None]
    fresh = max(fr_vals) if fr_vals else None
    fnote = (f"from source date; half-life {settings.half_lives.get(c.category)} days ({c.category})" if fresh is not None
             else "unknown: no publication/update date available on decisive sources" if decisive else "no decisive evidence")
    conf, breakdown = confidence(decisive, status)
    return ClaimReport(c.to_dict(), status, fresh, fnote, conf, breakdown, expl.strip(), [asdict(r) for r in records],
                       correction, q, out.status)


def confidence(decisive: list[EvidenceRecord], status: str) -> tuple[float | None, dict]:
    if not decisive:
        return None, {"note": "no decisive evidence"}
    a = max(r.authority for r in decisive)
    rel = sum(r.relevance for r in decisive) / len(decisive)
    spec = 1.0 if any(r.replacement or "matches" in r.relevance_explanation or "states" in r.relevance_explanation or "names" in r.relevance_explanation for r in decisive) else 0.6
    corr = min(len({r.domain for r in decisive}), 3) / 3
    dated = 1.0 if any(r.published_date for r in decisive) else 0.0
    conflict = 1.0 if status == "CONFLICTING_EVIDENCE" else 0.0
    parts = {"authority": round(35 * a, 1), "relevance": round(25 * rel, 1), "specificity": round(15 * spec, 1),
             "corroboration": round(15 * corr, 1), "date_known": round(10 * dated, 1), "conflict_penalty": -30 * conflict}
    return round(max(0.0, sum(parts.values())), 1), parts


# ----------------------------------------------------------------------------- orchestration
def analyze(answer: str, question: str | None = None, urls: list[str] | None = None, preferred: list[str] | None = None,
            mode: str = "live", fixture: Path | None = None, now: datetime | None = None, search=None) -> dict:
    if len(answer) > 20000:
        raise ValueError("answer too long (max 20000 chars)")
    claims = extract_claims(answer)
    user_sources, url_errors = [], []
    for u in (urls or [])[:5]:
        try:
            title, text, pub = fetch_url(u)
            user_sources.append((u, title, text, pub))
        except (SecurityError, httpx.HTTPError) as e:
            url_errors.append({"url": u, "error": str(e)[:200]})
    if search is None:
        if mode == "fixture":
            search = FixtureSearch(fixture or ROOT / "demos" / "stale_fixtures" / "demo2.json")
        else:
            search = TavilyClient()
    origin = "fixture" if isinstance(search, FixtureSearch) else "live_tavily"
    reports = [verify_claim(c, search, user_sources, preferred or [], now, origin) for c in claims]
    counts: dict[str, int] = {}
    for r in reports:
        counts[r.status] = counts.get(r.status, 0) + 1
    aid = db.new_id("ans_")
    summary = {"total_claims": len(claims), "requiring_verification": sum(c.requires_verification for c in claims),
               "by_status": counts, "evidence_mode": origin, "search_calls": search.calls,
               "tavily_configured": bool(settings.tavily_api_key), "url_errors": url_errors}
    result = {"id": aid, "answer": answer, "question": question, "summary": summary, "claims": [asdict(r) for r in reports],
              "methodology": __doc__}
    _persist(result)
    return result


def _persist(res: dict) -> None:
    with db.tx() as c:
        c.execute("INSERT INTO analyses(id,answer,question,evidence_mode,created_at,summary_json,corrected_json) VALUES(?,?,?,?,strftime('%s','now'),?,?)",
                  (res["id"], res["answer"], res["question"], res["summary"]["evidence_mode"], db.dumps(res["summary"]), None))
        for r in res["claims"]:
            cl = r["claim"]
            c.execute("INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (db.new_id("clm_"), res["id"], cl["claim_id"], cl["claim"], cl["category"], cl["volatility"],
                       int(cl["requires_verification"]), r["status"], r["freshness"], r["confidence"], r["explanation"], db.dumps(r)))
            for e in r["evidence"]:
                c.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (db.new_id("ev_"), res["id"], cl["claim_id"], e["title"], e["url"], e["domain"], e["source_type"],
                           e["authority"], e["retrieved_at"], e["published_date"], e["excerpt"], e["relevance_explanation"],
                           e["outcome"], e["origin"]))


def load_analysis(aid: str) -> dict | None:
    a = db.row("SELECT * FROM analyses WHERE id=?", (aid,))
    if not a:
        return None
    claims = [db.loads(r["detail_json"]) for r in db.rows("SELECT detail_json FROM claims WHERE analysis_id=? ORDER BY claim_id", (aid,))]
    return {"id": aid, "answer": a["answer"], "question": a["question"], "summary": db.loads(a["summary_json"]),
            "claims": claims, "corrected": db.loads(a["corrected_json"]), "created_at": a["created_at"]}


def corrected_answer(aid: str) -> dict:
    """Evidence-based correction: only CONTRADICTED claims with an extracted replacement value are changed;
    unresolved claims are marked; every change cites its source. Original text is preserved alongside."""
    a = load_analysis(aid)
    if not a:
        raise KeyError(aid)
    text = a["answer"]
    citations, changes = [], []
    for r in a["claims"]:
        cl = r["claim"]
        sent = cl["claim"]
        if sent not in re.sub(r"\s+", " ", text):
            continue
        text = re.sub(r"\s+", " ", text)
        if r["status"] == "CONTRADICTED" and r.get("correction"):
            ev = next((e for e in r["evidence"] if e["outcome"] == "contradict"), None)
            old_vals = [v for vs in cl["values"].values() for v in vs]
            old = next((v.split()[-1] for v in old_vals if v.split()[-1] in sent), None)
            new_sent = sent.replace(old, r["correction"].split()[-1], 1) if old else sent
            if new_sent == sent:
                continue
            citations.append({"n": len(citations) + 1, "url": ev["url"] if ev else None, "title": ev["title"] if ev else None,
                              "origin": ev["origin"] if ev else None})
            text = text.replace(sent, f"{new_sent} [{len(citations)}]", 1)
            changes.append({"claim_id": cl["claim_id"], "original": sent, "corrected": new_sent, "citation": len(citations)})
        elif r["status"] in ("UNVERIFIED", "CONFLICTING_EVIDENCE", "POTENTIALLY_STALE"):
            text = text.replace(sent, f"{sent} [{r['status'].lower().replace('_', ' ')}]", 1)
            changes.append({"claim_id": cl["claim_id"], "original": sent, "corrected": None, "marked": r["status"]})
    out = {"original": a["answer"], "corrected": text, "changes": changes, "citations": citations,
           "policy": "Only contradicted claims with an evidence-extracted replacement are rewritten; others are marked, never invented."}
    with db.tx() as c:
        c.execute("UPDATE analyses SET corrected_json=? WHERE id=?", (db.dumps(out), aid))
    return out
