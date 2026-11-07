"""Module D - Tavily live search provider.

Verified against the official OpenAPI spec (docs.tavily.com/documentation/api-reference/openapi.json):
  POST https://api.tavily.com/search   Authorization: Bearer <TAVILY_API_KEY>
    body used: query (<400 chars), search_depth, topic (general|news|finance), max_results (0-20),
               include_domains + include_domains_mode ("prefer" boosts without restricting),
               include_published_date, include_raw_content (false|"text"), include_usage
    result fields: title, url, content, score, raw_content, published_date; top-level usage.credits
  POST https://api.tavily.com/extract  body: urls[1-20], query (reranks chunks), chunks_per_source,
               format ("text"), include_usage -> results[{url, raw_content}], failed_results[{url, error}]
  Errors: 400/422 invalid, 401 key, 429 rate limit (Retry-After), 432 plan limit, 433 PAYG limit,
          434 live fetch unavailable, 5xx server.
Every request is recorded in `search_usage` (credits when returned). Failures are explicit states.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

from . import db
from .config import settings
from .security import redact

BASE_URL = "https://api.tavily.com"


class TavilyResult(BaseModel):
    title: str = ""
    url: str
    content: str = ""
    score: float | None = None
    raw_content: str | None = None
    published_date: str | None = None


class TavilyResponse(BaseModel):
    query: str = ""
    results: list[TavilyResult] = []
    response_time: float | str | None = None


class SearchOutcome(BaseModel):
    ok: bool
    status: str  # ok | missing_key | timeout | rate_limited | quota_exceeded | network_error | invalid_response | http_error | no_results
    detail: str = ""
    query: str = ""
    results: list[TavilyResult] = []
    retrieved_at: str = ""
    cached: bool = False
    credits: float | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def domain_of(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def record_search(endpoint: str, query: str, status: str, credits: float | None, cached: bool,
                  task_id: str | None = None, analysis_id: str | None = None) -> None:
    try:
        with db.tx() as c:
            c.execute("INSERT INTO search_usage(task_id,analysis_id,endpoint,query,status,credits,cached,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (task_id, analysis_id, endpoint, query[:300], status, credits, int(cached), time.time()))
    except Exception:
        pass


class TavilyClient:
    origin = "live_tavily"

    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None):
        self.api_key = api_key if api_key is not None else settings.tavily_api_key
        self.transport = transport  # injectable for tests
        self.calls = 0
        self.credits = 0.0

    def _post(self, path: str, payload: dict) -> httpx.Response:
        with httpx.Client(transport=self.transport, timeout=settings.tavily_timeout) as c:
            return c.post(f"{BASE_URL}{path}", json=payload,
                          headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})

    def search(self, query: str, include_domains: list[str] | None = None, max_results: int = 5,
               topic: str = "general", include_raw_content: bool = False, search_depth: str | None = None,
               use_cache: bool = True, domains_mode: str = "prefer") -> SearchOutcome:
        if not self.api_key:
            return SearchOutcome(ok=False, status="missing_key", query=query,
                                 detail="TAVILY_API_KEY is not set: live verification was not performed.")
        payload = {"query": query[:395], "max_results": max(1, min(max_results, 20)), "topic": topic,
                   "search_depth": search_depth or settings.tavily_search_depth,
                   "include_raw_content": "text" if include_raw_content else False,
                   "include_published_date": True, "include_usage": True}
        if include_domains:
            payload["include_domains"] = include_domains[:300]
            payload["include_domains_mode"] = domains_mode
        key = "tavily:" + hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if use_cache:
            hit = db.cache_get(key)
            if hit:
                out = SearchOutcome.model_validate(hit)
                out.cached = True
                record_search("search", query, "cache_hit", 0.0, True)
                return out
        last_status, last_detail = "network_error", ""
        for attempt in range(settings.tavily_max_retries + 1):
            try:
                self.calls += 1
                resp = self._post("/search", payload)
            except httpx.TimeoutException as e:
                last_status, last_detail = "timeout", f"timed out after {settings.tavily_timeout}s: {e}"
            except httpx.TransportError as e:
                last_status, last_detail = "network_error", redact(str(e))
            else:
                sc = resp.status_code
                if sc == 429:
                    last_status, last_detail = "rate_limited", "Tavily rate limit (HTTP 429)"
                    retry_after = resp.headers.get("retry-after")
                    time.sleep(min(float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt, 10))
                    continue
                if sc in (432, 433):
                    out = SearchOutcome(ok=False, status="quota_exceeded", query=query,
                                        detail=f"Tavily usage limit exceeded (HTTP {sc}: {'plan' if sc == 432 else 'pay-as-you-go'} limit)")
                    record_search("search", query, out.status, None, False)
                    return out
                if sc in (401, 403):
                    record_search("search", query, "auth_error", None, False)
                    return SearchOutcome(ok=False, status="http_error", query=query, detail=f"Tavily auth error HTTP {sc}: check TAVILY_API_KEY")
                if sc >= 500 or sc == 434:
                    last_status, last_detail = "http_error", f"Tavily HTTP {sc}"
                elif sc >= 400:
                    record_search("search", query, f"http_{sc}", None, False)
                    return SearchOutcome(ok=False, status="http_error", query=query, detail=f"Tavily HTTP {sc}: {redact(resp.text[:300])}")
                else:
                    try:
                        data = resp.json()
                        parsed = TavilyResponse.model_validate(data)
                    except (ValidationError, ValueError) as e:
                        record_search("search", query, "invalid_response", None, False)
                        return SearchOutcome(ok=False, status="invalid_response", query=query, detail=str(e)[:300])
                    credits = (data.get("usage") or {}).get("credits") if isinstance(data, dict) else None
                    if not isinstance(credits, (int, float)) or isinstance(credits, bool):
                        credits = None
                    if credits is not None:
                        self.credits += credits
                    out = SearchOutcome(ok=True, status="ok" if parsed.results else "no_results", query=query,
                                        results=parsed.results, retrieved_at=_now(), credits=credits)
                    db.cache_set(key, out.model_dump(), ttl=settings.cache_ttl_seconds)
                    record_search("search", query, out.status, credits, False)
                    return out
            if attempt < settings.tavily_max_retries:
                time.sleep(min(2 ** attempt, 4))
        record_search("search", query, last_status, None, False)
        return SearchOutcome(ok=False, status=last_status, query=query, detail=last_detail)

    def extract(self, urls: list[str], query: str | None = None) -> dict[str, str]:
        """Full page text for URLs via /extract (query reranks chunks). Returns {url: text}; failed URLs omitted."""
        if not self.api_key or not urls:
            return {}
        payload: dict = {"urls": urls[:20], "format": "text", "include_usage": True}
        if query:
            payload["query"] = query[:395]
            payload["chunks_per_source"] = 3
        key = "tavily-extract:" + hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        hit = db.cache_get(key)
        if hit is not None:
            return hit
        try:
            self.calls += 1
            resp = self._post("/extract", payload)
            if resp.status_code != 200:
                record_search("extract", ",".join(urls), f"http_{resp.status_code}", None, False)
                return {}
            data = resp.json()
            out = {r["url"]: r.get("raw_content") or "" for r in data.get("results", []) if "url" in r}
            credits = (data.get("usage") or {}).get("credits")
            if isinstance(credits, (int, float)):
                self.credits += credits
            record_search("extract", ",".join(urls), f"ok:{len(out)}/fail:{len(data.get('failed_results', []))}", credits, False)
            db.cache_set(key, out, ttl=settings.cache_ttl_seconds)
            return out
        except (httpx.HTTPError, ValueError, KeyError):
            record_search("extract", ",".join(urls), "error", None, False)
            return {}
