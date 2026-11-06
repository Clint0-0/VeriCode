"""Configurable LLM provider abstraction with token accounting.

Providers: anthropic (Messages API), openai (OpenAI-compatible chat completions), mock (scripted,
deterministic, DEMO ONLY - token counts are estimates, chars/4). No model ids are hardcoded:
they come from settings/env.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from . import db
from .config import settings
from .security import redact


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


def estimate_tokens(text: str) -> int:
    """Rough estimate (~4 chars/token). Always labelled as estimated."""
    return max(1, (len(text) + 3) // 4)


def record_usage(task_id: str | None, r: LLMResult, cached: bool = False) -> None:
    with db.tx() as c:
        c.execute(
            "INSERT INTO token_usage(task_id,stage,provider,model,input_tokens,output_tokens,estimated,cached,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (task_id, r.stage, r.provider, r.model, r.input_tokens, r.output_tokens, int(r.estimated), int(cached), time.time()),
        )


def _model_for(stage: str) -> str:
    if stage in ("planner", "claim_extraction", "claim_judge"):
        return settings.planner_model or settings.coder_model
    return settings.coder_model or settings.planner_model


def complete(system: str, prompt: str, stage: str, task_id: str | None = None, max_tokens: int = 4000,
             ledger: list | None = None) -> LLMResult:
    provider = settings.effective_provider()
    system, prompt = redact(system), redact(prompt)  # never send secrets to a model
    if provider == "none":
        raise LLMUnavailable("No LLM provider configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY (or enable VERICODE_DEMO_MODE=1 for scripted mock).")
    if provider == "mock":
        from .mock_provider import respond
        text = respond(stage, system, prompt)
        if text.startswith("MOCK_PROVIDER_NO_SCRIPT"):
            raise LLMUnavailable(text)
        r = LLMResult(text, estimate_tokens(system + prompt), estimate_tokens(text), True, "mock", "mock-scripted", stage)
    else:
        model = _model_for(stage)
        if not model:
            raise LLMUnavailable(f"No model configured for stage {stage}: set VERICODE_CODER_MODEL / VERICODE_PLANNER_MODEL")
        r = _call(provider, model, system, prompt, max_tokens, stage)
    record_usage(task_id, r)
    if ledger is not None:
        ledger.append(r)
    return r


def _call(provider: str, model: str, system: str, prompt: str, max_tokens: int, stage: str) -> LLMResult:
    last: Exception | None = None
    for attempt in range(3):
        try:
            if provider == "anthropic":
                if not settings.anthropic_api_key:
                    raise LLMUnavailable("ANTHROPIC_API_KEY not set")
                resp = httpx.post(
                    f"{settings.anthropic_base_url}/v1/messages",
                    headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": model, "max_tokens": max_tokens, "system": system,
                          "messages": [{"role": "user", "content": prompt}]},
                    timeout=180,
                )
                if resp.status_code in (429, 500, 502, 503, 529):
                    raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                resp.raise_for_status()
                d = resp.json()
                text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
                u = d.get("usage") or {}
                if "input_tokens" in u:
                    return LLMResult(text, u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0),
                                     u.get("output_tokens", 0), False, provider, model, stage)
                return LLMResult(text, estimate_tokens(system + prompt), estimate_tokens(text), True, provider, model, stage)
            if provider == "openai":
                if not settings.openai_api_key:
                    raise LLMUnavailable("OPENAI_API_KEY not set")
                resp = httpx.post(
                    f"{settings.openai_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    json={"model": model, "max_tokens": max_tokens,
                          "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
                    timeout=180,
                )
                if resp.status_code in (429, 500, 502, 503):
                    raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                resp.raise_for_status()
                d = resp.json()
                text = d["choices"][0]["message"]["content"] or ""
                u = d.get("usage") or {}
                if "prompt_tokens" in u:
                    return LLMResult(text, u["prompt_tokens"], u.get("completion_tokens", 0), False, provider, model, stage)
                return LLMResult(text, estimate_tokens(system + prompt), estimate_tokens(text), True, provider, model, stage)
            raise LLMUnavailable(f"unknown provider {provider}")
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            last = e
            time.sleep(2 ** attempt)
    raise LLMUnavailable(f"LLM call failed after retries: {redact(str(last))}")
