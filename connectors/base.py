"""
Base connector class for data sources.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
import hashlib
import time
import httpx
import asyncio
import os
from models.schema import Event, SeriesDescriptor, Source


@dataclass
class RawSeriesPayload:
    """Raw payload from a data source."""
    content: str
    content_type: str  # e.g., "text/calendar", "application/json", "text/html"
    url: str
    retrieved_at: datetime
    metadata: Dict[str, Any]


class Connector(ABC):
    """
    Abstract base class for motorsport data connectors.
    
    Each connector is responsible for:
    1. Fetching raw data from a specific source
    2. Extracting structured data from the raw payload
    3. Normalizing data to canonical schema
    """
    
    def __init__(self):
        self._cache: Dict[str, RawSeriesPayload] = {}
        self._last_request_time: float = 0
        self.rate_limit_seconds: float = 1.0  # Default: 1 request per second
        self.max_retries: int = 3  # Default: 3 retry attempts
        self.playwright_enabled: bool = os.getenv("PLAYWRIGHT_ENABLED", "true").lower() == "true"
    
    @property
    @abstractmethod
    def id(self) -> str:
        """Unique connector identifier."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable connector name."""
        pass
    
    @abstractmethod
    def supported_series(self) -> List[SeriesDescriptor]:
        """
        Return list of series this connector supports.
        
        Returns:
            List of SeriesDescriptor objects
        """
        pass
    
    @abstractmethod
    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        """
        Fetch raw data for a series season.
        
        Args:
            series_id: Series identifier
            season: Season year
            
        Returns:
            RawSeriesPayload containing fetched data
            
        Raises:
            ValueError: If series_id not supported
            httpx.HTTPError: If fetch fails
        """
        pass
    
    @abstractmethod
    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        """
        Extract events from raw payload.
        
        Args:
            raw: Raw payload from fetch_season
            
        Returns:
            List of Event objects
        """
        pass
    
    def normalize(self, events: List[Event]) -> List[Event]:
        """
        Normalize events to canonical schema.
        Default implementation does nothing - override if needed.
        
        Args:
            events: List of extracted events
            
        Returns:
            Normalized events
        """
        return events
    
    def health_check(self) -> bool:
        """
        Check if connector is healthy and can fetch data.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Try to get supported series
            series = self.supported_series()
            return len(series) > 0
        except Exception:
            return False
    
    def _get_cache_key(self, series_id: str, season: int) -> str:
        """Generate cache key for series/season."""
        return f"{self.id}:{series_id}:{season}"
    
    def _get_from_cache(self, series_id: str, season: int) -> Optional[RawSeriesPayload]:
        """Get cached payload if available."""
        key = self._get_cache_key(series_id, season)
        return self._cache.get(key)
    
    def _save_to_cache(self, series_id: str, season: int, payload: RawSeriesPayload):
        """Save payload to cache."""
        key = self._get_cache_key(series_id, season)
        self._cache[key] = payload
    
    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request_time = time.time()
    
    def _http_get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ) -> httpx.Response:
        """
        Make HTTP GET request with rate limiting and retries.
        
        Args:
            url: URL to fetch
            headers: Optional HTTP headers
            timeout: Request timeout in seconds
            
        Returns:
            Response object
            
        Raises:
            httpx.HTTPError: On request failure
        """
        self._rate_limit()
        
        # Set up default headers
        default_headers = {
            "User-Agent": "RaceBotDataCollector/1.0 (Educational/Personal Use)"
        }
        if headers:
            default_headers.update(headers)
        
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(follow_redirects=True) as client:
                    response = client.get(url, timeout=timeout, headers=default_headers)
                    response.raise_for_status()
                    return response
            except httpx.HTTPError as e:
                if attempt == self.max_retries - 1:
                    raise
                wait_time = 2 ** attempt
                time.sleep(wait_time)  # Exponential backoff
        
        # Should never reach here, but satisfy type checker
        raise httpx.HTTPError(f"Failed to fetch {url} after {self.max_retries} attempts")

    
    def create_source(
        self, 
        url: str, 
        retrieved_at: Optional[datetime] = None,
        extraction_method: Optional[str] = None,
        discovered_endpoints: Optional[List[str]] = None,
    ) -> Source:
        """
       Helper to create Source metadata.
        
        Args:
            url: Source URL
            retrieved_at: Retrieval timestamp (defaults to now)
            extraction_method: How data was extracted ("http", "playwright_network", etc.)
            discovered_endpoints: List of discovered API endpoints
            
        Returns:
            Source object
        """
        return Source(
            url=url,
            provider_name=self.name,
            retrieved_at=retrieved_at or datetime.utcnow(),
            raw_ref=None,
            extraction_method=extraction_method or "http",
            discovered_endpoints=discovered_endpoints or [],
        )
    
    # ------------------------------------------------------------------
    # Playwright Integration (optional, requires PLAYWRIGHT_ENABLED=true)
    # ------------------------------------------------------------------
    
    async def _playwright_get(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: float = 30.0,
    ):
        """
        Fetch a page using Playwright browser automation.
        
        Args:
            url: URL to fetch
            wait_for: CSS selector to wait for
            timeout: Request timeout in seconds
            
        Returns:
            RenderedPage object from browser_client
            
        Raises:
            RuntimeError: If Playwright not enabled
            ImportError: If playwright not installed
        """
        if not self.playwright_enabled:
            raise RuntimeError(
                "Playwright is disabled. Set PLAYWRIGHT_ENABLED=true to enable."
            )
        
        try:
            from browser_client import fetch_rendered_with_retry
        except ImportError:
            raise ImportError(
                "playwright not installed. Run: pip install 'playwright>=1.40.0' && playwright install chromium"
            )
        
        return await fetch_rendered_with_retry(
            url,
            wait_for=wait_for,
            timeout_ms=int(timeout * 1000),
        )
    
    async def _capture_endpoints(
        self,
        url: str,
        patterns: Optional[List[str]] = None,
    ):
        """
        Capture network responses that match patterns (e.g., JSON endpoints).
        
        Args:
            url: Page URL to load
            patterns: URL patterns to capture (e.g., ["schedule", "session"])
            
        Returns:
            List of CapturedResponse objects
            
        Raises:
            RuntimeError: If Playwright not enabled
        """
        if not self.playwright_enabled:
            raise RuntimeError(
                "Playwright is disabled. Set PLAYWRIGHT_ENABLED=true to enable."
            )
        
        try:
            from browser_client import capture_json_responses, discover_schedule_endpoints
        except ImportError:
            raise ImportError(
                "playwright not installed. Run: pip install 'playwright>=1.40.0' && playwright install chromium"
            )
        
        responses = await capture_json_responses(url, patterns=patterns)
        
        # Rank by likelihood of being schedule data
        scored = discover_schedule_endpoints(responses)
        
        # Return top matches
        return [resp for resp, score in scored if score > 2.0]
    
    def _run_async(self, coro):
        """
        Run async coroutine in sync context (with Streamlit compatibility).
        
        Helper for connectors that need to call async _playwright_get or _capture_endpoints
        from synchronous fetch_season methods.
        
        Uses threading to handle cases where an event loop is already running (e.g., Streamlit).
        """
        import threading
        
        try:
            # Try to get the running loop (works in Streamlit)
            loop = asyncio.get_running_loop()
            
            # If we're already in an event loop (Streamlit), run in thread
            result = None
            exception = None
            done_event = threading.Event()
            
            def run_in_thread():
                nonlocal result, exception
                try:
                    # Create new event loop for this thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    result = new_loop.run_until_complete(coro)
                    new_loop.close()
                except Exception as e:
                    exception = e
                finally:
                    done_event.set()
            
            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join()
            
            if exception:
                raise exception
            return result
            
        except RuntimeError:
            # No event loop running — create new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
