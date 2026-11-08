"""Regression tests for defects found during the live Groq/Tavily validation run (fake transports, no network)."""
import json
from pathlib import Path

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


def test_duration_parsing():
    assert llm._duration("7.66s") == pytest.approx(7.66)
    assert llm._duration("1m2.5s") == pytest.approx(62.5)
    assert llm._duration("450ms") == pytest.approx(0.45)
    assert llm._duration("20") == 20 and llm._duration(None) is None and llm._duration("soon") is None


def test_short_rate_limit_is_waited_out_then_succeeds(openai_groq, monkeypatch):
    slept, n = [], []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))

    def h(req):
        n.append(1)
        if len(n) < 3:
            return httpx.Response(429, headers={"x-ratelimit-reset-tokens": "12.5s"}, json={})
        return httpx.Response(200, headers={"x-ratelimit-remaining-tokens": "7000"},
                              json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                                    "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    r = llm.complete("s", "p", "planner", transport=httpx.MockTransport(h))
    assert r.text == "ok" and len(n) == 3 and slept == [13.0, 13.0]
    assert llm.last_rate_limits["x-ratelimit-remaining-tokens"] == "7000"


def test_long_rate_limit_stops_immediately_with_limits(openai_groq):
    n = []
    h = lambda req: (n.append(1), httpx.Response(429, headers={"retry-after": "3600", "x-ratelimit-limit-tokens": "200000"}, json={}))[1]
    with pytest.raises(llm.LLMUnavailable, match=r"retry after 3600s.*x-ratelimit-limit-tokens"):
        llm.complete("s", "p", "planner", transport=httpx.MockTransport(h))
    assert len(n) == 1  # no repeated hammering against a daily cap


def test_structured_effort_only_on_structured_stages_and_dropped_if_rejected(openai_groq, monkeypatch):
    monkeypatch.setattr(settings, "structured_reasoning_effort", "low")
    llm._effort_rejected.clear()
    bodies = []
    h = lambda req: (bodies.append(json.loads(req.content)), _resp("ok", "stop", 1))[1]
    llm.complete("s", "p", "planner", transport=httpx.MockTransport(h))
    llm.complete("s", "p", "coder", transport=httpx.MockTransport(h))
    assert bodies[0]["reasoning_effort"] == "low" and "reasoning_effort" not in bodies[1]

    seen = []

    def reject(req):
        b = json.loads(req.content)
        seen.append("reasoning_effort" in b)
        if "reasoning_effort" in b:
            return httpx.Response(400, json={"error": {"message": "`reasoning_effort` is not supported with this model"}})
        return _resp("ok", "stop", 1)
    monkeypatch.setattr(settings, "planner_model", "other-model")
    assert llm.complete("s", "p", "planner", transport=httpx.MockTransport(reject)).text == "ok"
    assert seen == [True, False]
    llm._effort_rejected.clear()


def test_retry_after_wins_over_irrelevant_request_window_reset(openai_groq, monkeypatch):
    """Live: Groq sent retry-after 7 with x-ratelimit-reset-requests 25m55s while 982 requests remained; the old code
    took the max (1555s) and gave up instead of waiting 7s."""
    slept, n = [], []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    hdr = {"retry-after": "7", "x-ratelimit-remaining-requests": "982", "x-ratelimit-reset-requests": "25m55.199s",
           "x-ratelimit-remaining-tokens": "360", "x-ratelimit-reset-tokens": "57.3s"}
    h = lambda req: (n.append(1), httpx.Response(429, headers=hdr, json={}) if len(n) == 1 else _resp("ok", "stop", 1))[1]
    assert llm.complete("s", "p", "planner", transport=httpx.MockTransport(h)).text == "ok"
    assert slept == [7.5]


def test_positional_values_accepted_for_varargs_decorator(sample_project):
    from vericode.repo_intel import inspect_project
    from vericode.skeleton import PlannedAPI, PlannedPackage
    from vericode.verify_api import verify_planned_api
    env = inspect_project(sample_project)

    def check(name, args):
        a = PlannedAPI(import_path="pydantic", name=name, type="function", arguments=args)
        return verify_planned_api(env, PlannedPackage(package="pydantic", ecosystem="python", assumed_version="2", planned_apis=[a]), a)

    assert check("field_serializer", ["'due'", "mode='plain'"]).status == "VERIFIED_LOCAL"  # live false INCOMPATIBLE
    assert check("field_serializer", ["bogus_kw=1"]).status == "INCOMPATIBLE"
    assert check("Field", ["min_length", "regex"]).status == "INCOMPATIBLE"  # real v1 kwarg still caught


TS = Path(__file__).resolve().parents[2] / "demos" / "ts_project"


@pytest.mark.skipif(not (TS / "node_modules" / "zod").is_dir(), reason="ts_project dependencies not installed")
@pytest.mark.parametrize("name,args,expected", [
    ("z.object", ["{ PORT: z.string() }"], "VERIFIED_LOCAL"),   # live: TS2344 + "Cannot find name 'z'" -> INCOMPATIBLE
    ("z.coerce.number", [], "VERIFIED_LOCAL"),                  # live: "z has no member 'coerce.number'" -> NOT_FOUND
    ("z.string", [], "VERIFIED_LOCAL"),                         # live: empty args type-checked as a 0-arg call
    ("z.object", ["{ PORT: schema }"], "VERIFIED_LOCAL"),       # planner-side identifier -> uncertain argument only
    ("z.coerce.bogus", [], "NOT_FOUND"),
    ("z.object", ["42"], "INCOMPATIBLE"),
    ("ZodString.nonempty", [], "DEPRECATED"),
    ("z.coerce.number.int", [], "VERIFIED_LOCAL"),             # live: chained call result member -> NOT_FOUND
    ("z.coerce.number.min", ["1"], "VERIFIED_LOCAL"),
    ("z.coerce.number.min", ["'x'"], "INCOMPATIBLE"),
    ("z.string.nonempty", [], "DEPRECATED"),                   # chain resolution exposes the real deprecation
    ("z.string.bogus", [], "NOT_FOUND"),
])
def test_ts_namespace_members_and_member_paths(name, args, expected):
    from vericode.repo_intel import inspect_project
    from vericode.skeleton import PlannedAPI, PlannedPackage
    from vericode.verify_api import verify_planned_api
    env = inspect_project(TS)
    a = PlannedAPI(import_path="zod", name=name, type="function", arguments=args)
    f = verify_planned_api(env, PlannedPackage(package="zod", ecosystem="node", assumed_version="3.23", planned_apis=[a]), a)
    assert f.status == expected, f.explanation
