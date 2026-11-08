"""Configurable LLM provider abstraction with token accounting.

Providers
  anthropic : Messages API  POST {base}/v1/messages  (x-api-key, anthropic-version: 2023-06-01)
              usage.input_tokens / output_tokens (+ cache_read_input_tokens / cache_creation_input_tokens)
  openai    : Chat Completions  POST {base}/chat/completions  (Authorization: Bearer)
              usage.prompt_tokens / completion_tokens. `max_completion_tokens` is sent to api.openai.com
              (current parameter); OpenAI-compatible gateways receive `max_tokens`.
  mock      : scripted, deterministic, DEMO ONLY - counts are estimates and labelled MOCK.

Measurement labels per call: ACTUAL_PROVIDER_USAGE | ESTIMATED (real provider, no usage returned) | MOCK.
Model ids are never hardcoded. A failing real provider raises LLMUnavailable - it never falls back to mock.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from . import db
from .config import settings
from .security import redact

ACTUAL, ESTIMATED, MOCK = "ACTUAL_PROVIDER_USAGE", "ESTIMATED", "MOCK"


class LLMUnavailable(Exception):
    pass


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    estimated: bool
    provider: str
    model: str
    stage: str
    truncated: bool = False  # provider stopped at the output-token limit (finish_reason=length / max_tokens)

    @property
    def measurement(self) -> str:
        if self.provider == "mock":
            return MOCK
        return ESTIMATED if self.estimated else ACTUAL


def measurement_of(ledger: list[LLMResult]) -> str:
    kinds = {r.measurement for r in ledger}
    if not kinds:
        return "NO_LLM_CALLS"
    if MOCK in kinds:
        return MOCK
    if ESTIMATED in kinds:
        return ESTIMATED
    return ACTUAL


def _valid_count(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _anthropic_usage(u: dict) -> tuple[int, int] | None:
    keys = ("input_tokens", "output_tokens")
    if not all(_valid_count(u.get(k)) for k in keys):
        return None
    extra = sum(u.get(k, 0) for k in ("cache_read_input_tokens", "cache_creation_input_tokens") if _valid_count(u.get(k, 0)))
    return u["input_tokens"] + extra, u["output_tokens"]


def _openai_usage(u: dict) -> tuple[int, int] | None:
    if not (_valid_count(u.get("prompt_tokens")) and _valid_count(u.get("completion_tokens"))):
        return None
    return u["prompt_tokens"], u["completion_tokens"]


def estimate_tokens(text: str) -> int:
    """Rough estimate (~4 chars/token). Always labelled as estimated."""
    return max(1, (len(text) + 3) // 4)


def record_usage(task_id: str | None, r: LLMResult, cached: bool = False) -> None:
    with db.tx() as c:
        c.execute(
            "INSERT INTO token_usage(task_id,stage,provider,model,input_tokens,output_tokens,estimated,cached,created_at,measurement) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (task_id, r.stage, r.provider, r.model, r.input_tokens, r.output_tokens, int(r.estimated), int(cached), time.time(), r.measurement),
        )


PLANNER_STAGES = ("planner", "claim_extraction", "claim_judge")


def model_for(stage: str) -> str:
    if stage in PLANNER_STAGES:
        return settings.planner_model or settings.coder_model
    return settings.coder_model or settings.planner_model


def provider_status() -> dict:
    p = settings.effective_provider()
    key = {"anthropic": settings.anthropic_api_key, "openai": settings.openai_api_key}.get(p)
    ready = p == "mock" or (p in ("anthropic", "openai") and bool(key) and bool(settings.coder_model or settings.planner_model))
    missing = []
    if p == "anthropic" and not key:
        missing.append("ANTHROPIC_API_KEY")
    if p == "openai" and not key:
        missing.append("OPENAI_API_KEY")
    if p in ("anthropic", "openai") and not (settings.coder_model or settings.planner_model):
        missing.append("VERICODE_CODER_MODEL")
    if p == "none":
        missing += ["ANTHROPIC_API_KEY or OPENAI_API_KEY", "VERICODE_CODER_MODEL"]
    return {"provider": p, "ready": ready, "missing": missing, "real": p in ("anthropic", "openai"),
            "planner_model": model_for("planner") if p != "mock" else "mock-scripted",
            "coder_model": model_for("coder") if p != "mock" else "mock-scripted"}


MAX_OUTPUT_BUDGET = 8192


def complete(system: str, prompt: str, stage: str, task_id: str | None = None, max_tokens: int = 4000,
             ledger: list | None = None, transport: httpx.BaseTransport | None = None) -> LLMResult:
    provider = settings.effective_provider()
    system, prompt = redact(system), redact(prompt)  # never send secrets to a model
    if provider == "none":
        raise LLMUnavailable("No LLM provider configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY plus VERICODE_CODER_MODEL "
                             "(or VERICODE_LLM_PROVIDER=mock for the scripted offline demo).")
    if provider == "mock":
        from .mock_provider import respond
        text = respond(stage, system, prompt)
        if text.startswith("MOCK_PROVIDER_NO_SCRIPT"):
            raise LLMUnavailable(text)
        r = LLMResult(text, estimate_tokens(system + prompt), estimate_tokens(text), True, "mock", "mock-scripted", stage)
    else:
        model = model_for(stage)
        if not model:
            raise LLMUnavailable(f"No model configured for stage {stage}: set VERICODE_CODER_MODEL / VERICODE_PLANNER_MODEL")
        r = _call(provider, model, system, prompt, max_tokens, stage, transport)
        if r.truncated and max_tokens < MAX_OUTPUT_BUDGET:
            # Output hit the token limit (reasoning models spend part of it on hidden reasoning). The truncated call's
            # tokens were really consumed: record them, then retry ONCE with a larger budget.
            r.text = r.text or ""
            record_usage(task_id, r)
            if ledger is not None:
                ledger.append(r)
            r = _call(provider, model, system, prompt, min(max_tokens * 2, MAX_OUTPUT_BUDGET), stage, transport)
        if r.truncated and not r.text.strip():
            record_usage(task_id, r)
            if ledger is not None:
                ledger.append(r)
            raise LLMUnavailable(f"{stage}: output token limit reached before any content was produced (finish_reason=length)")
    record_usage(task_id, r)
    if ledger is not None:
        ledger.append(r)
    return r


T = TypeVar("T", bound=BaseModel)


def extract_json_object(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        import re
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
        if m:
            text = m.group(1)
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start: i + 1])
    raise ValueError("unterminated JSON object")


def complete_json(system: str, prompt: str, schema: type[T], stage: str, task_id: str | None = None,
                  ledger: list | None = None, max_attempts: int = 2, max_tokens: int = 1500,
                  transport: httpx.BaseTransport | None = None) -> T:
    """Structured output: JSON validated against a Pydantic schema, bounded correction attempts."""
    hint = json.dumps(schema.model_json_schema())[:3000]
    sys2 = f"{system}\nRespond with ONE JSON object only, matching this JSON schema:\n{hint}"
    msg, last = prompt, ""
    for _ in range(max_attempts):
        r = complete(sys2, msg, stage, task_id, max_tokens, ledger, transport)
        try:
            return schema.model_validate(extract_json_object(r.text))
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last = str(e)[:500]
            msg = f"{prompt}\n\nYour previous reply was invalid ({last}). Reply with the corrected JSON object only."
    raise LLMUnavailable(f"{stage}: model output failed schema validation after {max_attempts} attempts: {last}")


def _sse_events(resp: httpx.Response):
    """Yield parsed JSON payloads from a server-sent-events response."""
    for line in resp.iter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def _stream_call(client: httpx.Client, provider: str, model: str, system: str, prompt: str, max_tokens: int,
                 stage: str) -> LLMResult:
    """Streaming variant (long coder generations): text deltas are accumulated; usage comes from the stream's
    usage events (Anthropic message_start/message_delta; OpenAI stream_options.include_usage final chunk)."""
    if provider == "anthropic":
        req = client.build_request("POST", f"{settings.anthropic_base_url}/v1/messages",
                                   headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                                            "content-type": "application/json"},
                                   json={"model": model, "max_tokens": max_tokens, "system": system, "stream": True,
                                         "messages": [{"role": "user", "content": prompt}]})
    else:
        limit_key = "max_completion_tokens" if "api.openai.com" in settings.openai_base_url else "max_tokens"
        req = client.build_request("POST", f"{settings.openai_base_url}/chat/completions",
                                   headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                                   json={"model": model, limit_key: max_tokens, "stream": True, "stream_options": {"include_usage": True},
                                         **_effort(stage, provider, model),
                                         "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
    resp = client.send(req, stream=True)
    try:
        if resp.status_code in (429, 500, 502, 503, 529):
            raise httpx.HTTPStatusError(f"retryable {resp.status_code}", request=req, response=resp)
        if resp.status_code >= 400:
            resp.read()
            raise LLMUnavailable(f"{provider} HTTP {resp.status_code}: {redact(resp.text[:400])}")
        text, tin, tout, have_usage, complete, cut = [], 0, 0, False, False, False
        for ev in _sse_events(resp):
            if provider == "anthropic":
                t = ev.get("type")
                if t == "message_start":
                    usage = _anthropic_usage((ev.get("message") or {}).get("usage") or {})
                    if usage:
                        tin, tout, have_usage = usage[0], usage[1], True
                elif t == "content_block_delta" and (ev.get("delta") or {}).get("type") == "text_delta":
                    text.append(ev["delta"].get("text", ""))
                elif t == "message_delta":
                    cut = cut or (ev.get("delta") or {}).get("stop_reason") == "max_tokens"
                    ot = (ev.get("usage") or {}).get("output_tokens")
                    if _valid_count(ot):
                        tout = ot
                elif t == "message_stop":
                    complete = True
                elif t == "error":
                    raise LLMUnavailable(f"anthropic stream error: {redact(json.dumps(ev.get('error'))[:300])}")
            else:
                for ch in ev.get("choices") or []:
                    text.append(((ch.get("delta") or {}).get("content")) or "")
                    if ch.get("finish_reason"):
                        complete = True
                        cut = cut or ch.get("finish_reason") == "length"
                usage = _openai_usage(ev.get("usage") or {}) if ev.get("usage") else None
                if usage:
                    tin, tout, have_usage = usage[0], usage[1], True
        out = "".join(text)
        if not complete:
            raise LLMUnavailable(f"{provider}: incomplete stream (connection ended before the completion event); partial output discarded")
        if not out.strip() and not cut:
            raise LLMUnavailable(f"{provider} returned empty content")
        if have_usage:
            return LLMResult(out, tin, tout, False, provider, model, stage, cut)
        return LLMResult(out, estimate_tokens(system + prompt), estimate_tokens(out), True, provider, model, stage, cut)
    finally:
        resp.close()


STRUCTURED_STAGES = ("planner", "claim_judge", "claim_extraction")
_effort_rejected: set[str] = set()  # models that returned 400 for reasoning_effort (sent once, then dropped)


def _effort(stage: str, provider: str, model: str | None = None) -> dict:
    """`reasoning_effort` for OpenAI-compatible endpoints: global setting, else the structured-stage setting for
    planner/judge/extraction. Coder and repair stages only ever get the global value, identical for baseline and
    VeriCode runs."""
    if provider != "openai" or (model and model in _effort_rejected):
        return {}
    v = settings.reasoning_effort or (settings.structured_reasoning_effort if stage in STRUCTURED_STAGES else "")
    return {"reasoning_effort": v} if v else {}


RATE_HEADERS = ("x-ratelimit-limit-requests", "x-ratelimit-remaining-requests", "x-ratelimit-reset-requests",
                "x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens", "x-ratelimit-reset-tokens", "retry-after")
last_rate_limits: dict = {}


def _duration(v: str | None) -> float | None:
    """Parse provider reset values: '20', '7.66s', '1m2.5s', '2h3m', '450ms'."""
    if not v:
        return None
    v = v.strip()
    try:
        return float(v)
    except ValueError:
        pass
    total, found = 0.0, False
    for num, unit in re.findall(r"([\d.]+)(ms|h|m|s)", v):
        found = True
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return total if found else None


def _note_limits(headers) -> None:
    got = {h: headers.get(h) for h in RATE_HEADERS if headers.get(h) is not None}
    if got:
        last_rate_limits.clear()
        last_rate_limits.update(got)


def _rate_wait(resp) -> float | None:
    """Seconds to wait after a 429. The provider's retry-after wins; otherwise use the reset of the quota that is
    actually exhausted (a request-window reset is irrelevant while requests remain, and vice versa)."""
    h = resp.headers
    ra = _duration(h.get("retry-after"))
    if ra is not None:
        return ra
    waits = []
    for kind in ("tokens", "requests"):
        rem = h.get(f"x-ratelimit-remaining-{kind}")
        reset = _duration(h.get(f"x-ratelimit-reset-{kind}"))
        if reset is not None and (rem is None or (rem.isdigit() and int(rem) <= 0) or kind == "tokens"):
            waits.append(reset)
    return min(waits) if waits else None


def _call(provider: str, model: str, system: str, prompt: str, max_tokens: int, stage: str,
          transport: httpx.BaseTransport | None = None) -> LLMResult:
    last: Exception | None = None
    timeout = httpx.Timeout(settings.llm_timeout, connect=15)
    key = {"anthropic": settings.anthropic_api_key, "openai": settings.openai_api_key}.get(provider)
    if provider in ("anthropic", "openai") and not key:  # fail fast: no network/TLS setup without credentials
        raise LLMUnavailable(f"{provider.upper()}_API_KEY not set")
    attempt, rl_waits = 0, 0
    while attempt < 3:
        try:
            with httpx.Client(transport=transport, timeout=timeout) as client:
                if settings.llm_stream and stage in ("coder", "repair") and provider in ("anthropic", "openai"):
                    if not (settings.anthropic_api_key if provider == "anthropic" else settings.openai_api_key):
                        raise LLMUnavailable(f"{provider.upper()}_API_KEY not set")
                    return _stream_call(client, provider, model, system, prompt, max_tokens, stage)
                if provider == "anthropic":
                    if not settings.anthropic_api_key:
                        raise LLMUnavailable("ANTHROPIC_API_KEY not set")
                    resp = client.post(
                        f"{settings.anthropic_base_url}/v1/messages",
                        headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                                 "content-type": "application/json"},
                        json={"model": model, "max_tokens": max_tokens, "system": system,
                              "messages": [{"role": "user", "content": prompt}]},
                    )
                    if resp.status_code in (429, 500, 502, 503, 529):
                        raise httpx.HTTPStatusError(f"retryable {resp.status_code}", request=resp.request, response=resp)
                    if resp.status_code >= 400:
                        raise LLMUnavailable(f"Anthropic HTTP {resp.status_code}: {redact(resp.text[:400])}")
                    d = resp.json()
                    if not isinstance(d, dict) or not isinstance(d.get("content"), list):
                        raise ValueError("missing 'content' list")
                    text = "".join(b.get("text", "") for b in d["content"] if isinstance(b, dict) and b.get("type") == "text")
                    if not text.strip():
                        raise LLMUnavailable(f"Anthropic returned empty content (stop_reason={d.get('stop_reason')})")
                    usage = _anthropic_usage(d.get("usage") or {})
                    cut = d.get("stop_reason") == "max_tokens"
                    if usage:
                        return LLMResult(text, usage[0], usage[1], False, provider, model, stage, cut)
                    return LLMResult(text, estimate_tokens(system + prompt), estimate_tokens(text), True, provider, model, stage, cut)
                if provider == "openai":
                    if not settings.openai_api_key:
                        raise LLMUnavailable("OPENAI_API_KEY not set")
                    limit_key = "max_completion_tokens" if "api.openai.com" in settings.openai_base_url else "max_tokens"
                    resp = client.post(
                        f"{settings.openai_base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                        json={"model": model, limit_key: max_tokens,
                              **_effort(stage, provider, model),
                              "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
                    )
                    if resp.status_code in (429, 500, 502, 503):
                        raise httpx.HTTPStatusError(f"retryable {resp.status_code}", request=resp.request, response=resp)
                    if resp.status_code == 400 and "reasoning_effort" in resp.text and _effort(stage, provider, model):
                        _effort_rejected.add(model)  # model does not accept the parameter: drop it, retry once
                        continue
                    if resp.status_code >= 400:
                        raise LLMUnavailable(f"OpenAI HTTP {resp.status_code}: {redact(resp.text[:400])}")
                    _note_limits(resp.headers)
                    d = resp.json()
                    text = d["choices"][0]["message"].get("content") or ""
                    finish = d["choices"][0].get("finish_reason")
                    if not text.strip() and finish != "length":
                        raise LLMUnavailable(f"OpenAI returned empty content (finish_reason={finish})")
                    usage = _openai_usage(d.get("usage") or {})
                    if usage:
                        return LLMResult(text, usage[0], usage[1], False, provider, model, stage, finish == "length")
                    return LLMResult(text, estimate_tokens(system + prompt), estimate_tokens(text), True, provider, model, stage, finish == "length")
                raise LLMUnavailable(f"unknown provider {provider}")
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            last = e
            r = getattr(e, "response", None) if isinstance(e, httpx.HTTPStatusError) else None
            if r is not None and r.status_code == 429:
                _note_limits(r.headers)
                w = _rate_wait(r)
                # short reset (per-minute limits): wait it out, bounded; long reset (daily cap): stop now, report it
                if w is not None and w <= settings.rate_limit_max_wait and rl_waits < settings.rate_limit_max_waits:
                    rl_waits += 1
                    time.sleep(w + 0.5)
                    continue
                break
            attempt += 1
            if attempt < 3:
                time.sleep(2 ** (attempt - 1))
        except (KeyError, ValueError) as e:
            raise LLMUnavailable(f"{provider}: unexpected response format: {e}")
    resp = getattr(last, "response", None)
    if resp is not None and resp.status_code == 429:
        w = _rate_wait(resp)
        lim = {k: resp.headers.get(k) for k in RATE_HEADERS if resp.headers.get(k) is not None}
        raise LLMUnavailable(f"{provider}: rate limited (HTTP 429) after retries"
                             + (f"; provider asks to retry after {w:g}s" if w is not None else "")
                             + (f"; limits {lim}" if lim else "")
                             + ". Account quota or per-minute limit reached; wait and re-run.")
    raise LLMUnavailable(f"LLM call failed after retries: {redact(str(last))}")
