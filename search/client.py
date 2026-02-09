"""
SearchClient ABC and provider implementations.

Supports:
  - SerpAPI (default, wraps Google/Bing)
  - Bing Web Search API
  - Google Programmable Search Engine API

API keys are read from environment or Streamlit secrets.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import httpx


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------

@dataclass
class SearchResult:
    """Single search hit."""

    title: str
    url: str
    snippet: str
    published_at: Optional[datetime] = None
    # populated later by ranking
    score: float = 0.0
    tier: Optional[str] = None


@dataclass
class SearchProvenance:
    """Provenance record for one search call."""

    query: str
    provider: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    result_count: int = 0
    chosen_urls: List[str] = field(default_factory=list)
    scoring_reasons: List[str] = field(default_factory=list)


# ------------------------------------------------------------------
# Abstract client
# ------------------------------------------------------------------

class SearchClient(ABC):
    """Abstract search interface."""

    def __init__(self, rate_limit: float = 1.0):
        self._last_request: float = 0
        self._rate_limit = rate_limit  # seconds between calls
        self._cache: Dict[str, List[SearchResult]] = {}
        self._cache_ttl: float = 3600  # 1h default
        self._cache_ts: Dict[str, float] = {}

    @abstractmethod
    def _do_search(
        self,
        query: str,
        count: int,
        recency_days: Optional[int],
    ) -> List[SearchResult]:
        """Provider-specific search implementation."""
        ...

    def search(
        self,
        query: str,
        count: int = 10,
        recency_days: Optional[int] = None,
    ) -> List[SearchResult]:
        """
        Public search entry point with caching + rate limiting.
        """
        cache_key = f"{query}::{count}::{recency_days}"
        if cache_key in self._cache:
            ts = self._cache_ts.get(cache_key, 0)
            if time.time() - ts < self._cache_ttl:
                return self._cache[cache_key]

        # rate limit
        elapsed = time.time() - self._last_request
        if elapsed < self._rate_limit:
            time.sleep(self._rate_limit - elapsed)
        self._last_request = time.time()

        results = self._do_search(query, count, recency_days)
        self._cache[cache_key] = results
        self._cache_ts[cache_key] = time.time()
        return results

    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...


# ------------------------------------------------------------------
# SerpAPI provider (wraps Google)
# ------------------------------------------------------------------

class SerpAPIClient(SearchClient):
    """Search via SerpAPI (https://serpapi.com)."""

    API_URL = "https://serpapi.com/search"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key or os.environ.get("SERPAPI_KEY", "")

    @property
    def provider_name(self) -> str:
        return "serpapi"

    def _do_search(
        self,
        query: str,
        count: int,
        recency_days: Optional[int],
    ) -> List[SearchResult]:
        if not self._api_key:
            raise RuntimeError(
                "SERPAPI_KEY not set. Set env var or pass api_key."
            )

        params: dict = {
            "q": query,
            "api_key": self._api_key,
            "engine": "google",
            "num": min(count, 20),
        }
        if recency_days:
            params["tbs"] = f"qdr:d{recency_days}"

        with httpx.Client(timeout=30) as client:
            resp = client.get(self.API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: List[SearchResult] = []
        for item in data.get("organic_results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    published_at=_parse_date(item.get("date")),
                )
            )
        return results


# ------------------------------------------------------------------
# Bing Web Search API provider
# ------------------------------------------------------------------

class BingSearchClient(SearchClient):
    """Search via Bing Web Search v7."""

    API_URL = "https://api.bing.microsoft.com/v7.0/search"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key or os.environ.get("BING_SEARCH_KEY", "")

    @property
    def provider_name(self) -> str:
        return "bing"

    def _do_search(
        self,
        query: str,
        count: int,
        recency_days: Optional[int],
    ) -> List[SearchResult]:
        if not self._api_key:
            raise RuntimeError(
                "BING_SEARCH_KEY not set. Set env var or pass api_key."
            )

        headers = {"Ocp-Apim-Subscription-Key": self._api_key}
        params: dict = {"q": query, "count": min(count, 50)}
        if recency_days:
            params["freshness"] = "Day" if recency_days <= 1 else "Week" if recency_days <= 7 else "Month"

        with httpx.Client(timeout=30) as client:
            resp = client.get(self.API_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        results: List[SearchResult] = []
        for item in data.get("webPages", {}).get("value", []):
            results.append(
                SearchResult(
                    title=item.get("name", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                    published_at=_parse_date(item.get("dateLastCrawled")),
                )
            )
        return results


# ------------------------------------------------------------------
# Google Programmable Search Engine (CSE) provider
# ------------------------------------------------------------------

class GoogleCSEClient(SearchClient):
    """Search via Google Custom Search JSON API."""

    API_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        cx: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._api_key = api_key or os.environ.get("GOOGLE_CSE_KEY", "")
        self._cx = cx or os.environ.get("GOOGLE_CSE_CX", "")

    @property
    def provider_name(self) -> str:
        return "google_cse"

    def _do_search(
        self,
        query: str,
        count: int,
        recency_days: Optional[int],
    ) -> List[SearchResult]:
        if not self._api_key or not self._cx:
            raise RuntimeError(
                "GOOGLE_CSE_KEY and GOOGLE_CSE_CX not set."
            )

        params: dict = {
            "key": self._api_key,
            "cx": self._cx,
            "q": query,
            "num": min(count, 10),
        }
        if recency_days:
            params["dateRestrict"] = f"d{recency_days}"

        with httpx.Client(timeout=30) as client:
            resp = client.get(self.API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: List[SearchResult] = []
        for item in data.get("items", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                )
            )
        return results


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    """Best-effort date parsing."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    try:
        from dateutil.parser import parse as du_parse
        return du_parse(raw)
    except Exception:
        return None


def get_search_client(
    provider: str = "serpapi",
    api_key: Optional[str] = None,
    **kwargs,
) -> SearchClient:
    """Factory — create a search client by provider name."""
    providers = {
        "serpapi": SerpAPIClient,
        "bing": BingSearchClient,
        "google_cse": GoogleCSEClient,
    }
    cls = providers.get(provider)
    if not cls:
        raise ValueError(
            f"Unknown provider '{provider}'. Choose from: {list(providers.keys())}"
        )
    return cls(api_key=api_key, **kwargs)
