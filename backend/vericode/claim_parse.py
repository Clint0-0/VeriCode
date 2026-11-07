"""Deterministic clause decomposition and linguistic feature extraction for claim extraction.

Design: small, separately testable steps instead of one giant regex. Every produced piece records whether
its text is an exact substring of the sentence (`exact`, with sub-span) or was `derived` (a shared subject
was carried over from the same sentence). Nothing is resolved across sentences: pronoun subjects that
cannot be resolved inside the sentence are marked `incomplete` and never verified.

Steps
  1. split_subordinate : "Although X, Y" / "X, although Y" / "X because Y" / "X, whereas Y" -> X | Y
  2. split_relative    : "S, which V ..., V2 ..." (non-restrictive relative clause on the subject) -> S V2 | S V
  3. split_coordinated : coordinated predicates / clauses (claims.split_compound)
Features: hedging, hypotheticals, comparisons, quantities with units, version ranges, temporal markers,
qualifiers/exceptions, incomplete subjects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HEDGE = re.compile(r"\b(may|might|could|probably|likely|possibly|reportedly|allegedly|approximately|roughly|around|about|an estimated|"
                   r"appears? to|seems? to|is said to|is thought to|is believed to|up to|nearly|almost)\b", re.I)
HYPOTHETICAL = re.compile(r"\b(would|imagine|suppose|supposing|hypothetically|in theory|if [^,]* were)\b", re.I)
COMPARISON = re.compile(r"\b(\w+er than|more \w+ than|less \w+ than|fewer \w+ than|as \w+ as|compared (?:to|with)|outperforms?|"
                        r"the (?:largest|smallest|fastest|slowest|biggest|most|least) \w+)\b", re.I)
QUANTITY = re.compile(r"\b(\d+(?:[.,]\d+)?)\s?(%|percent|ms|s|seconds|minutes|hours|days|GB|TB|MB|KB|GHz|MHz|km|kg|mph|"
                      r"users|customers|employees|downloads|requests|tokens|million|billion|thousand|k)\b", re.I)
VERSION_RANGE = re.compile(r"(?:(>=|<=|>|<|==|~=|\^|~)\s?v?(\d+(?:\.\d+){0,2}))|\b(\d+\.\d+(?:\.\d+)?)\s?\+|"
                           r"\b(?:from|between)\s+v?(\d+\.\d+(?:\.\d+)?)\s+(?:to|and|through|-|–)\s+v?(\d+\.\d+(?:\.\d+)?)|"
                           r"\bv?(\d+\.\d+(?:\.\d+)?)\s?(?:-|–|to)\s?v?(\d+\.\d+(?:\.\d+)?)\b", re.I)
TEMPORAL_MARKERS = re.compile(r"\b(currently|latest|now|today|recently|previously|formerly|historically|originally|since \d{4}|"
                              r"as of [\w ]+?\d{4}|until \d{4}|no longer|still|newly|at present|this year|last year)\b", re.I)
PAST_STATE = re.compile(r"\b(previously|formerly|originally|historically|used to|was once|in the past)\b", re.I)
QUALIFIER = re.compile(r"\b(except(?: for)?|excluding|other than|with the exception of|apart from|only (?:for|in|on|when)|"
                       r"unless|in most cases|in some cases|for (?:most|some|many) \w+)\b", re.I)
PRONOUN_SUBJECT = re.compile(r"^\s*(it|they|this|these|that|those|he|she|its|their)\b", re.I)

SUBORD_LEAD = re.compile(r"^\s*(although|though|even though|while|whereas|because|since)\s+(?P<sub>[^,]+),\s*(?P<main>.+)$", re.I)
SUBORD_TRAIL = re.compile(r"^(?P<main>.+?),?\s+(?P<conj>although|though|even though|whereas|because)\s+(?P<sub>.+)$", re.I)
RELATIVE = re.compile(r"^(?P<subj>[^,]{2,60}?),\s+which\s+(?P<rel>[^,]+),\s+(?P<rest>.+)$", re.I)


@dataclass
class Piece:
    text: str
    start: int | None  # offset inside the sentence when `exact`
    exact: bool
    relation: str = ""  # e.g. "subordinate:because", "relative", "main"
    notes: list[str] = field(default_factory=list)


def _clean(t: str) -> str:
    t = t.strip().strip(",").strip()
    if t and t[-1] not in ".!?":
        t += "."
    return t[0].upper() + t[1:] if t else t


def _piece(sentence: str, text: str, relation: str) -> Piece:
    raw = text.strip().rstrip(".").strip(",").strip()
    idx = sentence.find(raw)
    return Piece(_clean(raw), idx if idx >= 0 else None, idx >= 0, relation)


def split_subordinate(sentence: str) -> list[Piece]:
    """Split concessive/contrastive/causal subordinate clauses. Time/conditional clauses ("when", "if") are
    NOT split: they qualify the main claim and must stay attached to it."""
    m = SUBORD_LEAD.match(sentence)
    if m:
        conj, sub = m.group(1).lower(), m.group("sub").strip()
        is_time_phrase = conj == "since" and re.match(r"\d{4}\b", sub)
        if not is_time_phrase and len(sub.split()) >= 3 and len(m.group("main").split()) >= 3:
            return [_piece(sentence, m.group("main"), "main"), _piece(sentence, sub, f"subordinate:{conj}")]
    m = SUBORD_TRAIL.match(sentence)
    if m and len(m.group("sub").split()) >= 3 and len(m.group("main").split()) >= 3:
        conj = m.group("conj").lower()
        p = [_piece(sentence, m.group("main"), "main"), _piece(sentence, m.group("sub"), f"subordinate:{conj}")]
        if conj == "because":
            p[1].notes.append("causal link itself is not verified; only the stated fact is")
        return p
    return [Piece(sentence, 0, True, "main")]


def split_relative(piece: Piece) -> list[Piece]:
    """'Python 3.12, which was released in 2023, added X.' -> 'Python 3.12 added X.' + 'Python 3.12 was released in 2023.'
    Only when the relative clause directly follows the sentence subject (unambiguous attachment)."""
    m = RELATIVE.match(piece.text)
    if not m:
        return [piece]
    subj = m.group("subj").strip()
    if PRONOUN_SUBJECT.match(subj) or len(subj.split()) > 7:
        return [piece]
    main = Piece(_clean(f"{subj} {m.group('rest')}"), None, False, "main", ["subject shared with relative clause"])
    rel = Piece(_clean(f"{subj} {m.group('rel')}"), None, False, "relative", ["from non-restrictive relative clause"])
    return [main, rel]


def features(text: str) -> dict:
    vr = []
    for m in VERSION_RANGE.finditer(text):
        g = m.groups()
        if g[0]:
            vr.append(f"{g[0]}{g[1]}")
        elif g[2]:
            vr.append(f">={g[2]}")
        elif g[3]:
            vr.append(f"{g[3]}..{g[4]}")
        elif g[5]:
            vr.append(f"{g[5]}..{g[6]}")
    return {
        "hedged": bool(HEDGE.search(text)),
        "hedges": sorted({h.lower() for h in HEDGE.findall(text)})[:5],
        "hypothetical": bool(HYPOTHETICAL.search(text)),
        "comparison": [c if isinstance(c, str) else c[0] for c in COMPARISON.findall(text)][:3],
        "quantities": [f"{n} {u}" for n, u in QUANTITY.findall(text)][:6],
        "version_ranges": vr[:4],
        "temporal_markers": sorted({t.lower() for t in TEMPORAL_MARKERS.findall(text)})[:6],
        "past_state": bool(PAST_STATE.search(text)),
        "qualifiers": sorted({q.lower() for q in QUALIFIER.findall(text)})[:4],
        "incomplete": bool(PRONOUN_SUBJECT.match(text)),
    }
