"""Regression tests for defects found during the live Groq/Tavily validation run (fake transports, no network)."""
import json

import httpx
import pytest

from vericode import llm
from vericode.config import settings


@pytest.fixture
def openai_groq(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "gsk-test-000000000000000000")
    monkeypatch.setattr(settings, "openai_base_url", "https://api.groq.com/openai/v1")
    monkeypatch.setattr(settings, "coder_model", "m")
    monkeypatch.setattr(settings, "planner_model", "m")
    monkeypatch.setattr(settings, "llm_stream", False)
    monkeypatch.setattr(settings, "reasoning_effort", "")
    monkeypatch.setattr("time.sleep", lambda s: None)


def _resp(content, finish, out_tokens):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}],
                                     "usage": {"prompt_tokens": 10, "completion_tokens": out_tokens}})


def test_truncated_output_retried_once_with_larger_budget_and_both_calls_counted(openai_groq):
    seen = []

    def h(req):
        body = json.loads(req.content)
        seen.append(body["max_tokens"])
        return _resp('{"a": 1', "length", body["max_tokens"]) if len(seen) == 1 else _resp('{"a": 1}', "stop", 50)

    ledger = []
    r = llm.complete("s", "p", "planner", max_tokens=1200, ledger=ledger, transport=httpx.MockTransport(h))
    assert seen == [1200, 2400]
    assert r.text == '{"a": 1}' and not r.truncated
    assert [x.output_tokens for x in ledger] == [1200, 50]  # the truncated call's real usage is not hidden
    assert all(x.measurement == "ACTUAL_PROVIDER_USAGE" for x in ledger)


def test_empty_content_at_length_limit_is_reported_not_silently_empty(openai_groq):
    h = lambda req: _resp("", "length", json.loads(req.content)["max_tokens"])
    ledger = []
    with pytest.raises(llm.LLMUnavailable, match="output token limit"):
        llm.complete("s", "p", "planner", max_tokens=4096, ledger=ledger, transport=httpx.MockTransport(h))
    assert len(ledger) == 2


def test_empty_content_other_finish_reason_still_rejected(openai_groq):
    with pytest.raises(llm.LLMUnavailable, match="empty content"):
        llm.complete("s", "p", "planner", transport=httpx.MockTransport(lambda r: _resp("", "stop", 0)))


def test_reasoning_effort_sent_only_when_configured(openai_groq, monkeypatch):
    bodies = []
    h = lambda req: (bodies.append(json.loads(req.content)), _resp("ok", "stop", 1))[1]
    llm.complete("s", "p", "planner", transport=httpx.MockTransport(h))
    monkeypatch.setattr(settings, "reasoning_effort", "low")
    llm.complete("s", "p", "planner", transport=httpx.MockTransport(h))
    assert "reasoning_effort" not in bodies[0] and bodies[1]["reasoning_effort"] == "low"


def test_class_in_import_path_resolves_method(sample_project):
    """Live run: planner emitted import_path='pydantic.BaseModel', name='model_dump' and pre-flight wrongly said
    NOT_FOUND for pydantic 2.9.2, steering the coder into a bogus fallback."""
    from vericode.repo_intel import inspect_project
    from vericode.skeleton import PlannedAPI, PlannedPackage
    from vericode.verify_api import verify_planned_api
    env = inspect_project(sample_project)

    def check(ip, name):
        a = PlannedAPI(import_path=ip, name=name, type="method", arguments=[])
        return verify_planned_api(env, PlannedPackage(package="pydantic", ecosystem="python", assumed_version="2", planned_apis=[a]), a)

    assert check("pydantic.BaseModel", "model_dump").status == "VERIFIED_LOCAL"
    assert check("pydantic.BaseModel", "dict").status == "DEPRECATED"
    assert check("pydantic.BaseModel", "definitely_not_an_api").status == "NOT_FOUND"


def test_rate_limit_reported_clearly(openai_groq):
    h = lambda req: httpx.Response(429, headers={"retry-after": "37"}, json={})
    with pytest.raises(llm.LLMUnavailable, match=r"rate limited \(HTTP 429\).*retry after 37s"):
        llm.complete("s", "p", "planner", transport=httpx.MockTransport(h))
