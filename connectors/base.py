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

    
    def create_source(self, url: str, retrieved_at: Optional[datetime] = None) -> Source:
        """
       Helper to create Source metadata.
        
        Args:
            url: Source URL
            retrieved_at: Retrieval timestamp (defaults to now)
            
        Returns:
            Source object
        """
        return Source(
            url=url,
            provider_name=self.name,
            retrieved_at=retrieved_at or datetime.utcnow(),
            raw_ref=None
        )
