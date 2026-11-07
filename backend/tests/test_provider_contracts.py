"""Provider CONTRACT tests (controlled fake HTTP transports - NOT live integration tests).
They pin how VeriCode reacts to every response shape a provider can send."""
import json

import httpx
import pytest

from vericode import llm
from vericode.config import settings
from vericode.tavily import TavilyClient


def sse(events, done=True):
    body = "".join(f"data: {e if isinstance(e, str) else json.dumps(e)}\n\n" for e in events)
    return body + ("data: [DONE]\n\n" if done else "")


@pytest.fixture
def anthropic(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    monkeypatch.setattr(settings, "coder_model", "m")
    monkeypatch.setattr(settings, "llm_stream", False)
    monkeypatch.setattr("time.sleep", lambda s: None)


@pytest.fixture
def openai(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-00000000000000000000")
    monkeypatch.setattr(settings, "coder_model", "m")
    monkeypatch.setattr(settings, "llm_stream", False)
    monkeypatch.setattr("time.sleep", lambda s: None)


def call(handler, stage="coder"):
    return llm.complete("s", "p", stage, transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------- non-streaming
def test_anthropic_valid(anthropic):
    r = call(lambda q: httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 5, "output_tokens": 2}}))
    assert (r.text, r.measurement) == ("ok", "ACTUAL_PROVIDER_USAGE")


@pytest.mark.parametrize("resp,match", [
    (httpx.Response(200, text="<html>not json</html>"), "unexpected response format"),
    (httpx.Response(200, json={"content": []}), "empty"),
    (httpx.Response(200, json={"content": [{"type": "text", "text": ""}], "usage": {"input_tokens": 1, "output_tokens": 0}}), "empty"),
    (httpx.Response(401, json={"error": {"message": "invalid x-api-key"}}), "HTTP 401"),
    (httpx.Response(400, json={"error": {"message": "bad model"}}), "HTTP 400"),
])
def test_anthropic_errors(anthropic, resp, match):
    with pytest.raises(llm.LLMUnavailable, match=match):
        call(lambda q: resp)


def test_anthropic_invalid_usage(anthropic):
    r = call(lambda q: httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": "lots", "output_tokens": None}}))
    assert r.measurement == "ESTIMATED"


def test_openai_invalid_usage_and_missing_fields(openai):
    r = call(lambda q: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": -3}}))
    assert r.measurement == "ESTIMATED"
    with pytest.raises(llm.LLMUnavailable, match="unexpected response format"):
        call(lambda q: httpx.Response(200, json={"id": "x"}))
    with pytest.raises(llm.LLMUnavailable, match="empty"):
        call(lambda q: httpx.Response(200, json={"choices": [{"message": {"content": None}}]}))


def test_rate_limit_then_success_and_exhaustion(anthropic):
    n = {"c": 0}

    def flaky(q):
        n["c"] += 1
        return httpx.Response(429, headers={"retry-after": "2"}) if n["c"] < 3 else httpx.Response(
            200, json={"content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 1, "output_tokens": 1}})
    assert call(flaky).text == "ok" and n["c"] == 3
    with pytest.raises(llm.LLMUnavailable, match="failed after retries"):
        call(lambda q: httpx.Response(529, json={"error": "overloaded"}))


def test_server_error_and_timeout_exhaustion(openai):
    with pytest.raises(llm.LLMUnavailable, match="failed after retries"):
        call(lambda q: httpx.Response(503))

    def to(q):
        raise httpx.ConnectTimeout("connect timed out", request=q)
    with pytest.raises(llm.LLMUnavailable, match="failed after retries"):
        call(to)


def test_failing_real_provider_never_falls_back_to_mock(anthropic):
    with pytest.raises(llm.LLMUnavailable):
        call(lambda q: httpx.Response(500))
    from vericode import db
    assert db.row("SELECT COUNT(*) n FROM token_usage WHERE provider='mock'")["n"] == 0


def test_provider_switching(monkeypatch):
    monkeypatch.setattr(settings, "coder_model", "m")
    monkeypatch.setattr(settings, "llm_stream", False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-00000000000000000000")
    seen = []

    def h(q):
        seen.append(q.url.host)
        if "anthropic" in q.url.host:
            return httpx.Response(200, json={"content": [{"type": "text", "text": "a"}], "usage": {"input_tokens": 1, "output_tokens": 1}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "o"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    assert call(h).provider == "anthropic"
    monkeypatch.setattr(settings, "llm_provider", "openai")
    assert call(h).provider == "openai"
    assert seen == ["api.anthropic.com", "api.openai.com"]


def test_explicit_mock_mode_is_labelled(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    r = llm.complete("s", "TASK:\nAdd a priority_summary() method to TaskStore", "coder")
    assert r.provider == "mock" and r.measurement == "MOCK" and r.estimated


def test_mock_unsupported_task_error_is_helpful(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "mock")
    with pytest.raises(llm.LLMUnavailable) as e:
        llm.complete("s", "TASK:\nRefactor the billing module", "coder")
    msg = str(e.value)
    assert "MOCK_PROVIDER_NO_SCRIPT" in msg and "users" in msg and "ANTHROPIC_API_KEY" in msg


# ---------------------------------------------------------------- streaming
@pytest.fixture
def stream(monkeypatch):
    monkeypatch.setattr(settings, "llm_stream", True)


def test_anthropic_stream_unexpected_chunks_ignored(anthropic, stream):
    r = call(lambda q: httpx.Response(200, text=sse([
        "not-json", {"type": "ping"}, {"type": "message_start", "message": {"usage": {"input_tokens": 9, "output_tokens": 1}}},
        {"type": "content_block_start", "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hi"}},
        {"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "{"}},
        {"type": "message_delta", "usage": {"output_tokens": 4}}, {"type": "message_stop"}], done=False)))
    assert (r.text, r.input_tokens, r.output_tokens) == ("hi", 9, 4)


def test_anthropic_incomplete_stream_is_an_error(anthropic, stream):
    with pytest.raises(llm.LLMUnavailable, match="incomplete stream"):
        call(lambda q: httpx.Response(200, text=sse([
            {"type": "message_start", "message": {"usage": {"input_tokens": 9, "output_tokens": 1}}},
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "partial"}}], done=False)))


def test_anthropic_stream_error_event(anthropic, stream):
    with pytest.raises(llm.LLMUnavailable, match="stream error"):
        call(lambda q: httpx.Response(200, text=sse([{"type": "error", "error": {"type": "overloaded_error"}}], done=False)))


def test_openai_incomplete_stream_is_an_error(openai, stream):
    with pytest.raises(llm.LLMUnavailable, match="incomplete stream"):
        call(lambda q: httpx.Response(200, text=sse([{"choices": [{"delta": {"content": "par"}}]}], done=False)))


def test_openai_stream_complete_with_finish_reason(openai, stream):
    r = call(lambda q: httpx.Response(200, text=sse([{"choices": [{"delta": {"content": "x"}, "finish_reason": None}]},
                                                     {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                                                     {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 1}}])))
    assert (r.text, r.measurement) == ("x", "ACTUAL_PROVIDER_USAGE")


def test_stream_auth_failure_not_retried(anthropic, stream):
    n = {"c": 0}

    def h(q):
        n["c"] += 1
        return httpx.Response(401, json={"error": "bad key"})
    with pytest.raises(llm.LLMUnavailable, match="HTTP 401"):
        call(h)
    assert n["c"] == 1


# ---------------------------------------------------------------- structured output parser
def test_structured_parser_handles_braces_in_strings_and_fences():
    assert llm.extract_json_object('noise ```json\n{"a": "x}y{", "b": {"c": 1}}\n``` tail') == {"a": "x}y{", "b": {"c": 1}}
    assert llm.extract_json_object('{"q": "say \\"hi\\" {"}') == {"q": 'say "hi" {'}
    with pytest.raises(ValueError):
        llm.extract_json_object("no object here")
    with pytest.raises(ValueError):
        llm.extract_json_object('{"open": 1')


# ---------------------------------------------------------------- Tavily contracts
def tav(handler):
    return TavilyClient(api_key="tvly-contract-test", transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("resp,status", [
    (httpx.Response(200, text="not json"), "invalid_response"),
    (httpx.Response(200, json={"results": [{"title": "missing url"}]}), "invalid_response"),
    (httpx.Response(200, json={"results": []}), "no_results"),
    (httpx.Response(401, json={"detail": {"error": "Unauthorized"}}), "http_error"),
    (httpx.Response(432), "quota_exceeded"),
    (httpx.Response(433), "quota_exceeded"),
    (httpx.Response(422, json={"detail": "bad"}), "http_error"),
])
def test_tavily_response_contracts(resp, status, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert tav(lambda q: resp).search("q", use_cache=False).status == status


def test_tavily_invalid_usage_and_published_date(monkeypatch):
    out = tav(lambda q: httpx.Response(200, json={"results": [{"title": "t", "url": "https://x.org/a", "content": "c", "published_date": "2026-01-02"}],
                                                  "usage": {"credits": "free"}})).search("q", use_cache=False)
    assert out.ok and out.credits is None and out.results[0].published_date == "2026-01-02"


def test_tavily_server_error_exhaustion(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(settings, "tavily_max_retries", 2)
    n = {"c": 0}

    def h(q):
        n["c"] += 1
        return httpx.Response(502)
    out = tav(h).search("q", use_cache=False)
    assert out.status == "http_error" and n["c"] == 3


def test_tavily_extract_failed_results():
    c = tav(lambda q: httpx.Response(200, json={"results": [{"url": "https://a.org", "raw_content": "A"}],
                                                "failed_results": [{"url": "https://b.org", "error": "timeout"}]}))
    assert c.extract(["https://a.org", "https://b.org"]) == {"https://a.org": "A"}
