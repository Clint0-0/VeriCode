"""Module D - Tavily live search provider.

REST API: POST https://api.tavily.com/search and /extract, `Authorization: Bearer <TAVILY_API_KEY>`.
Search result fields used: title, url, content, score, raw_content (optional), published_date (optional,
mostly for topic="news"). Responses are validated; failures produce explicit unavailable states.
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
    status: str  # ok | missing_key | timeout | rate_limited | network_error | invalid_response | http_error | no_results
    detail: str = ""
    query: str = ""
    results: list[TavilyResult] = []
    retrieved_at: str = ""
    cached: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def domain_of(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


class TavilyClient:
    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None):
        self.api_key = api_key if api_key is not None else settings.tavily_api_key
        self.transport = transport  # injectable for tests
        self.calls = 0

    def _post(self, path: str, payload: dict) -> httpx.Response:
        with httpx.Client(transport=self.transport, timeout=settings.tavily_timeout) as c:
            return c.post(f"{BASE_URL}{path}", json=payload,
                          headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})

    def search(self, query: str, include_domains: list[str] | None = None, max_results: int = 5,
               topic: str = "general", include_raw_content: bool = False, search_depth: str = "basic",
               use_cache: bool = True) -> SearchOutcome:
        if not self.api_key:
            return SearchOutcome(ok=False, status="missing_key", query=query,
                                 detail="TAVILY_API_KEY is not set: live verification was not performed.")
        payload = {"query": query[:400], "max_results": max_results, "topic": topic,
                   "search_depth": search_depth, "include_raw_content": include_raw_content}
        if include_domains:
            payload["include_domains"] = include_domains
        key = "tavily:" + hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if use_cache:
            hit = db.cache_get(key)
            if hit:
                out = SearchOutcome.model_validate(hit)
                out.cached = True
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
                if resp.status_code == 429:
                    last_status, last_detail = "rate_limited", "Tavily rate limit (HTTP 429)"
                    retry_after = resp.headers.get("retry-after")
                    time.sleep(min(float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt, 10))
                    continue
                if resp.status_code in (401, 403):
                    return SearchOutcome(ok=False, status="http_error", query=query, detail=f"Tavily auth error HTTP {resp.status_code}")
                if resp.status_code >= 500:
                    last_status, last_detail = "http_error", f"Tavily HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    return SearchOutcome(ok=False, status="http_error", query=query, detail=f"Tavily HTTP {resp.status_code}: {redact(resp.text[:300])}")
                else:
                    try:
                        parsed = TavilyResponse.model_validate(resp.json())
                    except (ValidationError, ValueError) as e:
                        return SearchOutcome(ok=False, status="invalid_response", query=query, detail=str(e)[:300])
                    out = SearchOutcome(ok=True, status="ok" if parsed.results else "no_results", query=query,
                                        results=parsed.results, retrieved_at=_now())
                    db.cache_set(key, out.model_dump(), ttl=settings.cache_ttl_seconds)
                    return out
            if attempt < settings.tavily_max_retries:
                time.sleep(min(2 ** attempt, 4))
        return SearchOutcome(ok=False, status=last_status, query=query, detail=last_detail)

    def extract(self, urls: list[str]) -> dict[str, str]:
        """Fetch full page content for URLs via Tavily /extract. Returns {url: raw_content}."""
        if not self.api_key or not urls:
            return {}
        try:
            self.calls += 1
            resp = self._post("/extract", {"urls": urls[:5]})
            if resp.status_code != 200:
                return {}
            data = resp.json()
            return {r["url"]: r.get("raw_content") or "" for r in data.get("results", []) if "url" in r}
        except (httpx.HTTPError, ValueError, KeyError):
            return {}
