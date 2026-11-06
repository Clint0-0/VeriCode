import json
from datetime import datetime, timezone

import httpx
import pytest

from vericode import stale
from vericode.claims import extract_claims
from vericode.config import ROOT, settings
from vericode.tavily import TavilyClient

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)


def client_with(handler, key="tvly-test-key-123456"):
    return TavilyClient(api_key=key, transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- Tavily provider
def test_tavily_success_sends_bearer_and_validates():
    seen = {}

    def h(req: httpx.Request):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"query": "q", "results": [{"title": "T", "url": "https://docs.x.dev/a", "content": "c", "score": 0.9, "published_date": "2026-10-01"}]})
    out = client_with(h).search("pydantic field_validator", include_domains=["docs.pydantic.dev"], use_cache=False)
    assert out.ok and out.results[0].published_date == "2026-10-01"
    assert seen["auth"] == "Bearer tvly-test-key-123456"
    assert seen["body"]["include_domains"] == ["docs.pydantic.dev"] and seen["body"]["query"].startswith("pydantic")


def test_tavily_missing_key():
    out = TavilyClient(api_key="").search("x")
    assert not out.ok and out.status == "missing_key"


def test_tavily_timeout(monkeypatch):
    monkeypatch.setattr(settings, "tavily_max_retries", 1)
    monkeypatch.setattr("time.sleep", lambda s: None)

    def h(req):
        raise httpx.ReadTimeout("slow", request=req)
    c = client_with(h)
    out = c.search("x", use_cache=False)
    assert out.status == "timeout" and c.calls == 2  # bounded retries


def test_tavily_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "tavily_max_retries", 2)
    monkeypatch.setattr("time.sleep", lambda s: None)
    c = client_with(lambda r: httpx.Response(429, headers={"retry-after": "1"}))
    out = c.search("x", use_cache=False)
    assert out.status == "rate_limited" and c.calls == 3


def test_tavily_invalid_response():
    out = client_with(lambda r: httpx.Response(200, json={"results": [{"title": "no url"}]})).search("x", use_cache=False)
    assert out.status == "invalid_response"


def test_tavily_no_results_and_cache():
    calls = {"n": 0}

    def h(r):
        calls["n"] += 1
        return httpx.Response(200, json={"query": "x", "results": []})
    c = client_with(h)
    assert c.search("x").status == "no_results"
    again = c.search("x")
    assert again.cached and calls["n"] == 1


# ---------------------------------------------------------------- claim extraction
def test_claim_extraction_volatility():
    cs = extract_claims("ChatGPT Plus costs $20 per month. Water boils at 100 degrees Celsius at sea level. Satya Nadella is the CEO of Microsoft.")
    by = {c.claim[:10]: c for c in cs}
    assert by["ChatGPT Pl"].category == "pricing" and by["ChatGPT Pl"].volatility == "high" and by["ChatGPT Pl"].values["money"] == ["USD 20"]
    assert by["Water boil"].requires_verification is False
    assert by["Satya Nade"].category == "leadership"


def test_freshness_formula_and_unknown():
    f, age = stale.freshness("2026-08-09", "software_version", NOW)  # 90 days = one half-life
    assert age == 90 and f == 50.0
    assert stale.freshness(None, "pricing", NOW) == (None, None)


# ---------------------------------------------------------------- stale-answer verification
def fixture_file(tmp_path, sources, failure=None):
    p = tmp_path / "fx.json"
    p.write_text(json.dumps({"sources": sources, **({"simulate_failure": failure} if failure else {})}))
    return p


SRC_PRICE_NEW = {"title": "Pricing", "url": "https://openai.com/chatgpt/pricing", "published_date": "2026-10-01",
                 "keywords": ["chatgpt", "plus", "pricing"], "content": "ChatGPT Plus subscription is $25 per month."}
SRC_PRICE_OLD = {"title": "Old blog", "url": "https://help.openai.com/plus", "published_date": "2024-01-01",
                 "keywords": ["chatgpt", "plus", "pricing"], "content": "ChatGPT Plus subscription is $20 per month."}


def run(tmp_path, answer, sources, failure=None):
    return stale.analyze(answer, mode="fixture", fixture=fixture_file(tmp_path, sources, failure), now=NOW)


def test_current_supported(tmp_path):
    r = run(tmp_path, "ChatGPT Plus costs $25 per month.", [SRC_PRICE_NEW])
    c = r["claims"][0]
    assert c["status"] == "CURRENT_SUPPORTED" and c["freshness"] is not None and c["confidence"] > 50
    assert c["evidence"][0]["origin"] == "fixture" and c["evidence"][0]["url"].startswith("https://")


def test_outdated_contradicted_and_corrected(tmp_path):
    r = run(tmp_path, "ChatGPT Plus costs $20 per month.", [SRC_PRICE_NEW])
    c = r["claims"][0]
    assert c["status"] == "CONTRADICTED" and c["correction"] == "USD 25"
    corr = stale.corrected_answer(r["id"])
    assert "$25" in corr["corrected"] and "[1]" in corr["corrected"] and corr["original"].startswith("ChatGPT Plus costs $20")


def test_newer_evidence_supersedes_older(tmp_path):
    r = run(tmp_path, "ChatGPT Plus costs $20 per month.", [SRC_PRICE_NEW, SRC_PRICE_OLD])
    assert r["claims"][0]["status"] == "CONTRADICTED"


def test_conflicting_sources(tmp_path):
    undated = dict(SRC_PRICE_OLD, published_date=None, url="https://openai.com/plus-faq")
    r = run(tmp_path, "ChatGPT Plus costs $20 per month.", [SRC_PRICE_NEW, undated])
    c = r["claims"][0]
    assert c["status"] == "CONFLICTING_EVIDENCE" and c["confidence_breakdown"]["conflict_penalty"] == -30


def test_absence_of_support_is_never_contradiction(tmp_path):
    unrelated = dict(SRC_PRICE_NEW, content="ChatGPT Plus subscribers get access to new features.")
    r = run(tmp_path, "ChatGPT Plus currently includes priority access during peak times.", [unrelated])
    assert r["claims"][0]["status"] == "UNVERIFIED" and r["claims"][0]["missing_evidence"]


def test_insufficient_evidence_topic_only(tmp_path):
    topic_only = dict(SRC_PRICE_NEW, content="ChatGPT Plus pricing page lists several plans for subscribers.")
    r = run(tmp_path, "ChatGPT Plus costs $20 per month.", [topic_only])
    assert r["claims"][0]["status"] == "UNVERIFIED"


def test_stable_fact_not_applicable(tmp_path):
    r = run(tmp_path, "Python was created by Guido van Rossum.", [])
    assert r["claims"][0]["status"] == "NOT_APPLICABLE"


def test_missing_publication_date_freshness_unknown(tmp_path):
    r = run(tmp_path, "ChatGPT Plus costs $25 per month.", [dict(SRC_PRICE_NEW, published_date=None)])
    c = r["claims"][0]
    assert c["status"] == "CURRENT_SUPPORTED" and c["freshness"] is None and "unknown" in c["freshness_note"]


def test_old_support_for_present_tense_is_potentially_stale(tmp_path):
    r = run(tmp_path, "ChatGPT Plus costs $20 per month.", [SRC_PRICE_OLD])
    assert r["claims"][0]["status"] == "POTENTIALLY_STALE"


def test_network_failure_reports_unverified(tmp_path):
    r = run(tmp_path, "ChatGPT Plus costs $20 per month.", [], failure="network_error")
    c = r["claims"][0]
    assert c["status"] == "UNVERIFIED" and "could not be performed" in c["explanation"]


def test_live_mode_without_key_is_explicit(tmp_path):
    r = stale.analyze("ChatGPT Plus costs $20 per month.", mode="live")
    c = r["claims"][0]
    assert c["status"] == "UNVERIFIED" and c["search_status"] == "missing_key" and r["summary"]["evidence_mode"] == "live_tavily"


def test_demo2_fixture_end_to_end():
    d = json.loads((ROOT / "demos" / "stale_fixtures" / "demo2.json").read_text())
    r = stale.analyze(d["answer"], mode="fixture", now=NOW)
    st = [c["status"] for c in r["claims"]]
    assert st == ["CONTRADICTED", "CURRENT_SUPPORTED", "CURRENT_SUPPORTED", "CONTRADICTED", "UNVERIFIED", "NOT_APPLICABLE"]
    semantic_ok, semantic_neg = r["claims"][2], r["claims"][3]
    assert semantic_ok["evidence"][0]["method"] == "lexical" and semantic_ok["freshness"] is None  # docs page has no date
    assert semantic_neg["correction"] is None and "no replacement" in semantic_neg["missing_evidence"]
    assert stale.load_analysis(r["id"])["claims"][0]["evidence"]


def test_authority_ranking():
    assert stale.authority("https://www.irs.gov/x")[1] == "government"
    assert stale.authority("https://medium.com/x")[0] < stale.authority("https://docs.python.org/3/")[0]
    assert stale.authority("https://example.com", ["example.com"])[1] == "preferred_source"


def test_ssrf_blocked_for_user_urls(tmp_path):
    r = stale.analyze("ChatGPT Plus costs $20 per month.", urls=["http://127.0.0.1:8000/admin", "file:///etc/passwd"],
                      mode="fixture", fixture=fixture_file(tmp_path, []))
    assert len(r["summary"]["url_errors"]) == 2


def test_live_api_verification_uses_official_docs(sample_project):
    from vericode.repo_intel import inspect_project
    from vericode.skeleton import PlannedAPI, PlannedPackage, Skeleton
    from vericode.verify_api import verify_skeleton
    seen = {}

    def h(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"results": [{"title": "Validators - Pydantic", "url": "https://docs.pydantic.dev/latest/concepts/validators/",
                                                      "content": "Use field_validator ... the validator decorator is deprecated in V2.", "published_date": None}]})
    env = inspect_project(sample_project)
    sk = Skeleton(packages=[PlannedPackage(package="pydantic", ecosystem="python", assumed_version="1.10",
                                           planned_apis=[PlannedAPI(import_path="pydantic", name="validator", type="decorator")])])
    f = verify_skeleton(env, sk, client_with(h), live=True)[0]
    assert f.status == "DEPRECATED" and "tavily_live_search" in f.verification_method
    assert "docs.pydantic.dev" in seen["body"]["include_domains"]  # domain from installed package metadata
    assert f.live["sources"][0]["official"] and f.live["sources"][0]["mentions_api"]
