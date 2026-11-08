"""Regressions for the Track 1 weaknesses seen in the live Groq/Tavily run (scenarios B and D)."""
import json
from datetime import datetime, timezone

from vericode import stale

NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)


def run(tmp_path, answer, sources):
    p = tmp_path / "fx.json"
    p.write_text(json.dumps({"answer": answer, "sources": [{"keywords": [], "min_match": 1, **s} for s in sources]}))
    return stale.analyze(answer, mode="fixture", fixture=p, now=NOW)["claims"][0]


OLD_310 = {"title": "Python 3.10.0", "url": "https://www.python.org/downloads/release/python-3100/", "published_date": "2021-10-04",
           "keywords": ["python", "latest", "version"], "content": "Python 3.10.0 is the latest stable version of Python."}
UNDATED_313 = {"title": "Downloads", "url": "https://www.python.org/downloads/", "published_date": None,
               "keywords": ["python", "latest", "version"], "content": "The latest stable version of Python is Python 3.13.0."}


def test_B_outdated_latest_version_contradicted_by_newer_version_even_if_undated(tmp_path):
    c = run(tmp_path, "The latest stable version of Python is 3.10.", [OLD_310, UNDATED_313])
    assert c["status"] == "CONTRADICTED", c["explanation"]
    assert c["correction"] == "3.13"
    assert "newer version" in c["explanation"] and "correct when published" in c["explanation"]


def test_B_undated_lower_version_never_overrides_dated_current_evidence(tmp_path):
    new = dict(UNDATED_313, published_date="2025-10-07")
    undated_old = dict(OLD_310, published_date=None, url="https://www.python.org/old-page/")
    c = run(tmp_path, "The latest stable version of Python is 3.13.", [new, undated_old])
    assert c["status"] != "CONTRADICTED", c["explanation"]


def test_B_undated_price_does_not_override_dated_price(tmp_path):
    dated = {"title": "Pricing", "url": "https://acme.example/pricing", "published_date": "2026-09-01",
             "keywords": ["acme", "pro"], "content": "The Acme Pro plan costs $30 per month."}
    undated = {"title": "FAQ", "url": "https://docs.acme.example/faq", "published_date": None,
               "keywords": ["acme", "pro"], "content": "The Acme Pro plan costs $35 per month."}
    c = run(tmp_path, "The Acme Pro plan costs $30 per month.", [dated, undated])
    assert c["status"] == "CONFLICTING_EVIDENCE" and "no publication date" in c["conflict"]["reason"]


WEAK_NO = {"title": "Opinion", "url": "https://rust-takes.example.net/kernel", "published_date": "2026-01-10",
           "keywords": ["rust", "linux", "kernel"], "content": "Rust will not replace C in the Linux kernel by 2030."}


def test_D_weak_sources_alone_never_contradict(tmp_path):
    c = run(tmp_path, "Rust will replace C in the Linux kernel by 2030.", [WEAK_NO])
    assert c["status"] == "UNVERIFIED", c["explanation"]
    assert "low-authority" in c["explanation"] and c["missing_evidence"] == "no primary or secondary source settles the claim"
    assert c["correction"] is None


def test_D_weak_disagreement_both_sides_is_unverified_not_conflict(tmp_path):
    weak_yes = dict(WEAK_NO, url="https://kernel-blog.example.com/rust", content="Rust will replace C in the Linux kernel by 2030.")
    c = run(tmp_path, "Rust will replace C in the Linux kernel by 2030.", [WEAK_NO, weak_yes])
    assert c["status"] == "UNVERIFIED"


def test_D_weak_contradiction_set_aside_when_primary_supports(tmp_path):
    primary = {"title": "Pricing", "url": "https://acme.example/pricing", "published_date": "2026-09-01",
               "keywords": ["acme", "pro"], "content": "The Acme Pro plan costs $30 per month."}
    weak = {"title": "Forum", "url": "https://deals.example.org/acme", "published_date": "2026-10-01",
            "keywords": ["acme", "pro"], "content": "The Acme Pro plan costs $35 per month."}
    c = run(tmp_path, "The Acme Pro plan costs $30 per month.", [primary, weak])
    assert c["status"] == "CURRENT_SUPPORTED" and "set aside" in c["explanation"]


def test_product_names_map_to_publisher_domain():
    from vericode.source_authority import assess
    a = assess("https://openai.com/chatgpt/pricing", [], "pricing", "ChatGPT Plus costs $20 per month.", ["chatgpt", "plus"])
    assert a.tier == "primary" and a.matched_rule == "entity:openai"
    assert assess("https://openai-pricing.example.com/x", [], "pricing", "ChatGPT Plus costs $20.", []).tier != "primary"
