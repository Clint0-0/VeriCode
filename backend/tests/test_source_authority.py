"""Source-authority registry: exact/subdomain matching, impersonation, entity matching, tiers, and the rule that
authority never turns irrelevant evidence into support."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vericode import stale
from vericode.config import settings
from vericode.source_authority import assess, host_matches, impersonation, registrable

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)
FIX = json.loads((Path(__file__).parent / "data" / "authority_sources.json").read_text())


@pytest.mark.parametrize("host,pattern,ok", [
    ("docs.python.org", "python.org", True), ("python.org", "python.org", True), ("evilpython.org", "python.org", False),
    ("python.org.evil.net", "python.org", False), ("www.irs.gov", ".gov", True), ("gov", ".gov", False),
    ("notgov.com", ".gov", False), ("eur-lex.europa.eu", "europa.eu", True)])
def test_host_matching_is_exact_or_dot_bounded(host, pattern, ok):
    assert host_matches(host, pattern) is ok


def test_registrable_domain_handles_multi_part_tlds():
    assert registrable("www.gov.uk") == "www.gov.uk" or registrable("www.legislation.gov.uk") == "legislation.gov.uk"
    assert registrable("news.bbc.co.uk") == "bbc.co.uk" and registrable("docs.python.org") == "python.org"


@pytest.mark.parametrize("url,expected_tier,expected_type", [
    ("https://www.sec.gov/edgar", "primary", "government"),
    ("https://www.w3.org/TR/html52/", "primary", "standards"),
    ("https://docs.python.org/3/whatsnew/3.14.html", "primary", "official_software_docs"),
    ("https://pypi.org/project/pydantic/", "primary", "package_registry"),
    ("https://www.reuters.com/tech/x", "secondary", "news (secondary)"),
    ("https://en.wikipedia.org/wiki/X", "secondary", "encyclopedia (secondary)"),
    ("https://stackoverflow.com/q/1", "secondary", "community/blog (secondary)"),
    ("https://some-random-blog.example.com/post", "unknown", "unknown"),
    ("https://python.org.downloads-example.net/latest", "suspicious", "suspected_impersonation"),
    ("https://docs-python.org/3/", "suspicious", "suspected_impersonation"),
    ("https://pyth0n.org/downloads", "suspicious", "suspected_impersonation"),
])
def test_assess_tiers(url, expected_tier, expected_type):
    a = assess(url)
    assert (a.tier, a.source_type) == (expected_tier, expected_type), a
    assert a.explanation


def test_dotcom_is_not_official_without_entity_match():
    assert assess("https://www.example-reviews.com/chatgpt-plus-price", claim_text="ChatGPT Plus costs $20 per month.").tier == "unknown"
    a = assess("https://openai.com/chatgpt/pricing", claim_text="OpenAI charges $20 per month for ChatGPT Plus.")
    assert a.source_type == "official_entity_site" and "openai" in a.explanation


def test_category_rules_and_registry_are_configurable(monkeypatch):
    monkeypatch.setitem(settings.authority_rules, "pricing", ["vendor.test"])
    assert assess("https://shop.vendor.test/p", category="pricing").matched_rule == "category:pricing:vendor.test"
    monkeypatch.setattr(settings, "trusted_registry", {"standards": ["example-standards.org"]})
    assert assess("https://www.example-standards.org/spec").source_type == "standards"


def test_impersonation_helper():
    assert impersonation("python.org.mirror.example", ["python.org"])
    assert impersonation("docs.python.org", ["python.org"]) is None
    assert impersonation("pypi.org", ["python.org", "pypi.org"]) is None


def _run(tmp_path, ids, claim="Python 3.12 is the latest stable version of Python."):
    p = tmp_path / "f.json"
    p.write_text(json.dumps({"sources": [s for s in FIX["sources"] if s["id"] in ids]}))
    return stale.analyze(claim, mode="fixture", fixture=p, now=NOW)["claims"][0]


def test_unrelated_official_source_is_not_support(tmp_path):
    c = _run(tmp_path, ["unrelated_official"])
    assert c["status"] == "UNVERIFIED" and c["evidence"][0]["outcome"] == "irrelevant"
    assert c["evidence"][0]["authority_tier"] == "primary"  # authoritative publisher, but irrelevant content


def test_impersonation_never_decides(tmp_path):
    c = _run(tmp_path, ["impersonation"])
    assert c["status"] == "UNVERIFIED" and "ignored" in c["evidence"][0]["relevance_explanation"]
    assert c["evidence"][0]["authority_tier"] == "suspicious"


def test_official_beats_newer_community_post(tmp_path):
    c = _run(tmp_path, ["official", "community"])
    # community post is newer but lower authority -> conflict is surfaced, not silently resolved in its favour
    assert c["status"] == "CONFLICTING_EVIDENCE"
    assert "authority" in c["conflict"]["reason"]


def test_secondary_corroborates_primary(tmp_path):
    c = _run(tmp_path, ["official", "secondary"])
    assert c["status"] == "CONTRADICTED" and c["confidence_breakdown"]["corroboration"] == 10.0
    tiers = {e["domain"]: e["authority_tier"] for e in c["evidence"]}
    assert tiers == {"python.org": "primary", "en.wikipedia.org": "secondary"}


def test_authority_separate_from_freshness_and_confidence(tmp_path):
    c = _run(tmp_path, ["official"])
    assert c["freshness"] is not None and c["confidence"] is not None
    e = c["evidence"][0]
    assert e["authority"] == 0.95 and e["source_type"] == "primary_source_for_software_version" and e["freshness"] != e["authority"]
