"""Module E step 1 - deterministic claim extraction, categorisation and volatility assessment (no LLM)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

CATEGORY_RULES: list[tuple[str, re.Pattern]] = [
    ("pricing", re.compile(r"[$€£₹]\s?\d|\b\d+(\.\d+)?\s?(USD|EUR|GBP|INR|dollars?|euros?)\b|\bper (month|year|seat|user)\b|/mo(nth)?\b|\b(pric(e|es|ing)|costs?|subscription|fee)\b", re.I)),
    ("leadership", re.compile(r"\b(CEO|CTO|CFO|COO|president|chair(man|woman|person)?|prime minister|chief executive|head of|governor|minister)\b", re.I)),
    ("law_regulation", re.compile(r"\b(law|act|regulation|directive|GDPR|statute|legislation|bill|ordinance|tax rate|mandat(e|ory)|legal(ly)?)\b", re.I)),
    ("deadline", re.compile(r"\b(deadline|due (by|on)|no later than|expires?|end[- ]of[- ]life|EOL|sunset)\b", re.I)),
    ("software_version", re.compile(r"\b(version|v\d+|LTS|stable release|latest release|release candidate)\b|\b\d+\.\d+(\.\d+)?\b", re.I)),
    ("api_documentation", re.compile(r"\b(API|endpoint|SDK|function|method|parameter|deprecated|decorator|library|module)\b", re.I)),
    ("release_date", re.compile(r"\b(released|launched|announced|introduced|shipped|available since|debuted)\b", re.I)),
    ("product_spec", re.compile(r"\b\d+\s?(GB|TB|MB|MHz|GHz|mAh|inch(es)?|cores?|nm|W|Hz|tokens?)\b|\b(context window|battery|resolution|RAM)\b", re.I)),
    ("current_events", re.compile(r"\b(currently|right now|today|this (year|month|week)|recently|as of|ongoing)\b", re.I)),
]
TEMPORAL = re.compile(r"\b(latest|current(ly)?|now|newest|most recent|today|still|as of|is the|are the|costs?|plans? to|will|upcoming)\b", re.I)
PAST_EVENT = re.compile(r"\b(introduced|was released|released in|launched in|founded|created|invented|first)\b", re.I)
VOLATILITY = {"pricing": "high", "software_version": "high", "current_events": "high", "deadline": "high",
              "leadership": "medium", "law_regulation": "medium", "product_spec": "medium",
              "api_documentation": "medium", "release_date": "low", "other_volatile": "medium", "stable": "low"}

VERSION_RE = re.compile(r"\b[vV]?(\d+\.\d+(?:\.\d+)?(?:[a-z]+\d*)?)\b")
MONEY_RE = re.compile(r"([$€£₹])\s?(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s?(USD|EUR|GBP|INR)\b", re.I)
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
PERCENT_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s?%")
NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+(?:van|de|von|del|da)\b)?(?:\s+[A-Z][a-z]+)+)\b")

STOP = set("""a an the and or but of in on at to for from by with is are was were be been being it its this that these those
as into than then there their they he she we you i not no yes can could will would should may might must has have had do does did
which who whom whose what when where why how also very more most such only just about over under after before between known
called""".split())


@dataclass
class Claim:
    claim_id: str
    claim: str
    category: str
    volatility: str
    requires_verification: bool
    temporal: bool
    past_event: bool
    values: dict = field(default_factory=dict)
    subject_terms: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    # split on sentence punctuation followed by space + capital/digit/quote; ignore decimals like 3.12
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text)
    out = []
    for p in parts:
        out += [s.strip() for s in re.split(r";\s+", p) if s.strip()]
    return [s for s in out if len(s.split()) >= 3]


def extract_values(text: str) -> dict:
    vals: dict[str, list[str]] = {}
    money = []
    for m in MONEY_RE.finditer(text):
        money.append((m.group(1) or m.group(4) or "").upper().replace("$", "USD").replace("€", "EUR").replace("£", "GBP").replace("₹", "INR")
                     + " " + (m.group(2) or m.group(3)).replace(",", ""))
    if money:
        vals["money"] = money
    versions = [v for v in VERSION_RE.findall(text) if not MONEY_RE.search(v)]
    money_nums = {m.split()[-1] for m in money}
    versions = [v for v in versions if v not in money_nums]
    if versions:
        vals["version"] = versions
    years = YEAR_RE.findall(text)
    if years:
        vals["year"] = years
    pct = PERCENT_RE.findall(text)
    if pct:
        vals["percent"] = pct
    names = [n for n in NAME_RE.findall(text) if not re.match(r"^(The|This|In|As|On|At|Python|Java)\b", n)]
    if names:
        vals["name"] = names
    return vals


def subject_terms(text: str) -> list[str]:
    clean = VERSION_RE.sub(" ", MONEY_RE.sub(" ", text))
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#\-]{1,}", clean)
    seen, out = set(), []
    for w in words:
        lw = w.lower()
        if lw in STOP or len(lw) < 3 or lw in ("latest", "current", "currently", "stable", "version", "costs", "cost"):
            continue
        if lw not in seen:
            seen.add(lw)
            out.append(lw)
    return out[:12]


def categorize(sentence: str) -> tuple[str, str]:
    for cat, pat in CATEGORY_RULES:
        m = pat.search(sentence)
        if m:
            return cat, f"matched {cat} cue '{m.group(0)}'"
    if TEMPORAL.search(sentence):
        return "other_volatile", "temporal wording without a specific category"
    return "stable", "no volatile cue (definition/historical/general statement)"


def extract_claims(answer: str) -> list[Claim]:
    claims = []
    for i, s in enumerate(split_sentences(answer), 1):
        cat, why = categorize(s)
        temporal = bool(TEMPORAL.search(s))
        past = bool(PAST_EVENT.search(s)) and not re.search(r"\b(latest|current|now)\b", s, re.I)
        vol = VOLATILITY[cat]
        if temporal and vol == "medium":
            vol = "high"
        if past and vol == "high" and cat not in ("pricing",):
            vol = "medium"
        if cat == "stable" or (past and cat in ("release_date",) and not temporal):
            requires = cat != "stable"
        else:
            requires = True
        if cat == "stable":
            vol = "low"
        if s.endswith("?"):
            requires, vol, why = False, "low", "question, not a claim"
        claims.append(Claim(f"claim_{i:03d}", s, cat, vol, requires, temporal, past, extract_values(s), subject_terms(s), why))
    return claims
