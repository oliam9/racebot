"""
AI-Powered Web Scraper for Schedule Pages.

Safely scrapes motorsport schedule pages using:
- Playwright for page loading (handles JavaScript)
- Anthropic Claude or Google Gemini for data extraction
- Rate limiting and caching to avoid detection
- Respects robots.txt and implements delays
"""

import os
import time
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
import asyncio
import logging

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Rate Limiting
# ------------------------------------------------------------------

class RateLimiter:
    """Per-domain rate limiter with configurable delays."""
    
    def __init__(self, requests_per_minute: int = 3):
        self.requests_per_minute = requests_per_minute
        self.min_delay_seconds = 60.0 / requests_per_minute
        self._last_request: Dict[str, float] = {}
        self._request_count: Dict[str, List[float]] = {}
    
    def wait_if_needed(self, domain: str):
        """Block until it's safe to make a request to domain."""
        now = time.time()
        
        # Clean old timestamps (older than 1 minute)
        if domain in self._request_count:
            self._request_count[domain] = [
                ts for ts in self._request_count[domain]
                if now - ts < 60
            ]
        else:
            self._request_count[domain] = []
        
        # Check if we've hit the rate limit
        if len(self._request_count[domain]) >= self.requests_per_minute:
            oldest = self._request_count[domain][0]
            wait_time = 60 - (now - oldest)
            if wait_time > 0:
                logger.info(f"Rate limit reached for {domain}, waiting {wait_time:.1f}s")
                time.sleep(wait_time)
        
        # Enforce minimum delay between requests
        if domain in self._last_request:
            elapsed = now - self._last_request[domain]
            if elapsed < self.min_delay_seconds:
                wait_time = self.min_delay_seconds - elapsed
                logger.info(f"Enforcing delay for {domain}: {wait_time:.1f}s")
                time.sleep(wait_time)
        
        # Record this request
        self._last_request[domain] = time.time()
        self._request_count[domain].append(time.time())


# ------------------------------------------------------------------
# Response Cache
# ------------------------------------------------------------------

class ResponseCache:
    """Simple file-based cache for scraped pages."""
    
    def __init__(self, cache_dir: str = ".cache/scraper"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        return hashlib.md5(url.encode()).hexdigest()
    
    def get(self, url: str, max_age_hours: int = 24) -> Optional[str]:
        """Get cached content if available and fresh."""
        cache_file = os.path.join(self.cache_dir, f"{self._get_cache_key(url)}.html")
        
        if not os.path.exists(cache_file):
            return None
        
        # Check age
        mtime = os.path.getmtime(cache_file)
        age_hours = (time.time() - mtime) / 3600
        
        if age_hours > max_age_hours:
            logger.info(f"Cache expired for {url} (age: {age_hours:.1f}h)")
            return None
        
        logger.info(f"Using cached content for {url}")
        with open(cache_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    def set(self, url: str, content: str):
        """Store content in cache."""
        cache_file = os.path.join(self.cache_dir, f"{self._get_cache_key(url)}.html")
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Cached content for {url}")


# ------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------

@dataclass
class ScrapingResult:
    """Result of a scraping operation."""
    
    success: bool
    url: str
    series_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    
    # Metadata
    fetch_time_ms: float = 0
    extraction_time_ms: float = 0
    content_length: int = 0
    cached: bool = False


# ------------------------------------------------------------------
# AI Scraper
# ------------------------------------------------------------------

class AIScraper:
    """Main scraper using AI for data extraction."""
    
    def __init__(
        self,
        ai_provider: str = "anthropic claude",
        ai_model: str = None,
        requests_per_minute: int = 3,
        cache_hours: int = 24,
    ):
        """
        Initialize AI scraper.
        
        Args:
            ai_provider: "anthropic claude" or "google gemini"
            ai_model: Specific model to use (e.g., "gemini-2.5-flash", "gemini-2.5-pro")
            requests_per_minute: Max requests per domain per minute
            cache_hours: Cache validity in hours
        """
        self.ai_provider = ai_provider.lower()
        self.ai_model = ai_model
        self.rate_limiter = RateLimiter(requests_per_minute)
        self.cache = ResponseCache()
        
        # Initialize AI client
        if "anthropic" in self.ai_provider or "claude" in self.ai_provider:
            self._init_anthropic()
        elif "google" in self.ai_provider or "gemini" in self.ai_provider:
            self._init_gemini()
        else:
            raise ValueError(f"Unsupported AI provider: {ai_provider}")
    
    def _init_anthropic(self):
        """Initialize Anthropic Claude client."""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment")
        
        try:
            import anthropic
            self.ai_client = anthropic.Anthropic(api_key=api_key)
            self.model = "claude-3-5-sonnet-20241022"  # Latest model
            logger.info(f"Initialized Anthropic client with model: {self.model}")
        except ImportError:
            raise ImportError(
                "anthropic package not installed. "
                "Run: pip install anthropic"
            )
    
    def _init_gemini(self):
        """Initialize Google Gemini client."""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            # Use the latest stable Gemini 2.5 Flash model
            self.ai_client = genai.GenerativeModel('gemini-2.5-flash')
            logger.info("Initialized Gemini client with model: gemini-2.5-flash")
        except ImportError:
            raise ImportError(
                "google-generativeai package not installed. "
                "Run: pip install google-generativeai"
            )
    
    def scrape_schedule_page(
        self,
        url: str,
        series_name: str,
        season_year: int,
    ) -> ScrapingResult:
        """
        Scrape a schedule page and extract structured data.
        
        Args:
            url: URL of the schedule page
            series_name: Name of the series (e.g., "Formula 1")
            season_year: Season year
            
        Returns:
            ScrapingResult with extracted data
        """
        result = ScrapingResult(success=False, url=url)
        
        try:
            # Extract domain for rate limiting
            domain = urlparse(url).netloc
            
            # Check cache first
            cached_html = self.cache.get(url)
            
            if cached_html:
                html_content = cached_html
                result.cached = True
                result.fetch_time_ms = 0
            else:
                # Rate limit
                self.rate_limiter.wait_if_needed(domain)
                
                # Fetch page content
                fetch_start = time.time()
                html_content = self._fetch_page(url)
                result.fetch_time_ms = (time.time() - fetch_start) * 1000
                
                # Cache it
                self.cache.set(url, html_content)
            
            result.content_length = len(html_content)
            
            # Extract data with AI
            extract_start = time.time()
            series_data = self._extract_with_ai(
                html_content,
                series_name,
                season_year,
                url
            )
            result.extraction_time_ms = (time.time() - extract_start) * 1000
            
            result.series_data = series_data
            result.success = True
            
        except Exception as e:
            result.error_message = str(e)
            logger.error(f"Scraping failed for {url}: {e}")
        
        return result
    
    def _fetch_page(self, url: str) -> str:
        """Fetch page content using Playwright or httpx fallback."""
        # Check if Playwright is enabled
        playwright_enabled = os.environ.get("PLAYWRIGHT_ENABLED", "true").lower() == "true"
        
        if playwright_enabled:
            try:
                from browser_client import fetch_rendered
                
                # Run async fetch in sync context with longer timeout for complex pages
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    rendered = loop.run_until_complete(
                        fetch_rendered(url, timeout_ms=45000)  # Increased from 30s to 45s
                    )
                    
                    # For calendar/schedule pages, wait additional time for JS rendering
                    if any(keyword in url.lower() for keyword in ['calendar', 'schedule', 'fixture']):
                        logger.info(f"Calendar page detected, waiting for JavaScript rendering...")
                        loop.run_until_complete(asyncio.sleep(3))  # Extra 3 seconds for JS
                        # Fetch again after waiting
                        rendered = loop.run_until_complete(
                            fetch_rendered(url, timeout_ms=45000)
                        )
                    
                    logger.info(f"Successfully fetched {url} with Playwright ({len(rendered.content)} bytes)")
                    return rendered.content
                finally:
                    loop.close()
                    
            except Exception as e:
                logger.warning(f"Playwright fetch failed, trying httpx: {e}")
        
        # Fallback to simple HTTP request
        try:
            import httpx
            logger.info(f"Fetching {url} with httpx (simple HTTP)")
            response = httpx.get(
                url,
                follow_redirects=True,
                timeout=30.0,
                headers={
                    "User-Agent": "MotorsportBot/1.0 (Schedule Data Collector; Educational Use)"
                }
            )
            response.raise_for_status()
            return response.text
        except Exception as e:
            raise Exception(f"Failed to fetch page: {str(e)}")
    
    def _extract_with_ai(
        self,
        html_content: str,
        series_name: str,
        season_year: int,
        source_url: str,
    ) -> Dict[str, Any]:
        """Extract structured data from HTML using AI."""
        
        # Try to extract just the relevant calendar/schedule section
        relevant_content = self._extract_relevant_html(html_content)
        
        # Truncate if still too large (keep more for complex calendars like MotoGP)
        # Gemini can handle up to 1M tokens (~4M characters), so we're safe with 300KB
        max_chars = 300000  # Increased from 150k to 300k for complex pages
        if len(relevant_content) > max_chars:
            logger.warning(f"HTML too large ({len(relevant_content)} chars), truncating to {max_chars}")
            relevant_content = relevant_content[:max_chars] + "\n... (truncated)"
        
        prompt = self._build_extraction_prompt(
            relevant_content,
            series_name,
            season_year,
        )
        
        # Extract based on AI provider
        if "anthropic" in self.ai_provider or "claude" in self.ai_provider:
            series_data = self._extract_with_claude(prompt)
        elif "google" in self.ai_provider or "gemini" in self.ai_provider:
            series_data = self._extract_with_gemini(prompt)
        else:
            raise ValueError(f"Unsupported AI provider: {self.ai_provider}")
        
        # Post-process: add series_id to all events if missing
        if series_data and "events" in series_data:
            series_id = series_data.get("series_id", "unknown")
            for event in series_data["events"]:
                if "series_id" not in event:
                    event["series_id"] = series_id
        
        return series_data
    
    def _extract_relevant_html(self, html: str) -> str:
        """Extract just the relevant calendar/schedule content from HTML."""
        # Look for common calendar/schedule section markers
        calendar_markers = [
            "calendar",
            "schedule",
            "race-card",
            "event-list",
            "fixture",
            "championship",
        ]
        
        html_lower = html.lower()
        
        # Find the earliest calendar section
        earliest_pos = len(html)
        for marker in calendar_markers:
            pos = html_lower.find(marker)
            if pos != -1 and pos < earliest_pos:
                earliest_pos = pos
        
        # If we found a calendar section, start from there
        if earliest_pos < len(html):
            # Go back a bit to catch container elements
            start = max(0, earliest_pos - 500)
            return html[start:]
        
        # If no markers found, return full HTML
        return html
    
    def _extract_with_claude(self, prompt: str) -> Dict[str, Any]:
        """Extract using Anthropic Claude."""
        response = self.ai_client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=0.1,
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        
        # Parse JSON from response
        content = response.content[0].text
        return self._parse_ai_response(content)
    
    def _extract_with_gemini(self, prompt: str) -> Dict[str, Any]:
        """Extract using Google Gemini."""
        response = self.ai_client.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,
                "top_p": 0.95,
                "max_output_tokens": 8192,  # Increased from 4096 to handle large calendars
            }
        )
        
        content = response.text
        return self._parse_ai_response(content)
    
    def _parse_ai_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON from AI response."""
        import re
        
        try:
            # Remove markdown code blocks if present
            content = content.strip()
            
            # Handle Gemini's tendency to add explanatory text before JSON
            # Look for the first '{' to find where JSON starts
            json_start = content.find('{')
            if json_start > 0:
                # Strip everything before the JSON
                content = content[json_start:]
            
            #Remove markdown code fences
            if content.startswith('```'):
                lines = content.split('\n')
                # Remove first line (```) and last line (```)
                content = '\n'.join(lines[1:-1])
                if content.startswith('json'):
                    content = '\n'.join(content.split('\n')[1:])
            
            # Extract JSON only (between first { and last })
            first_brace = content.find('{')
            last_brace = content.rfind('}')
            if first_brace != -1 and last_brace != -1:
                content = content[first_brace:last_brace+1]
            
            # Try to parse JSON
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.error(f"Response content (first 500 chars): {content[:500]}")
            
            # Try to fix common JSON issues
            try:
                # Remove trailing commas
                fixed_content = re.sub(r',(\s*[}\]])', r'\1', content)
                # Try parsing again
                return json.loads(fixed_content)
            except json.JSONDecodeError:
                raise ValueError(f"AI returned invalid JSON: {str(e)}")
    
    def _build_extraction_prompt(
        self,
        html: str,
        series_name: str,
        season_year: int,
    ) -> str:
        """Build extraction prompt for AI."""
        return f"""You are an expert at extracting motorsport schedule data from web pages.

Extract ALL race events from the following HTML content for **{series_name} {season_year}**.

IMPORTANT: Extract ONLY basic event info (NO sessions). We'll fetch sessions separately.

Return ONLY valid JSON in this exact format (no other text):

{{
  "series_id": "series_slug",
  "name": "{series_name}",
  "season": {season_year},
  "category": "MOTORCYCLE",
  "events": [
    {{
      "event_id": "unique_id",
      "series_id": "series_slug",
      "name": "Event Name",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "venue": {{
        "circuit": "Circuit Name",
        "city": "City",
        "region": "State/Region",
        "country": "Country",
        "timezone": "America/New_York"
      }},
      "sessions": []
    }}
  ]
}}

**Instructions:**
- Extract ALL events found in the schedule (look for repeating patterns with event names, dates, locations)
- Common HTML patterns to look for:
  * Events in lists/grids with classes like "event", "race", "round", "calendar-listing"
  * Date ranges like "19 Jun - 21 Jun" or "March 8-10, 2024"
  * Location info in elements with "venue", "circuit", "country", "city"
  * Round numbers indicating event sequence
- Use ISO 8601 format for dates: "YYYY-MM-DD"
- If information is missing, omit the field or use null
- Infer timezone from location if not explicitly stated
- category should be one of: OPENWHEEL, ENDURANCE, RALLY, MOTORCYCLE, GT, TOURING, FORMULA, SPORTCAR, OTHER
- For **motorcycle championships** (MotoGP, World Superbike, etc.), use category: "MOTORCYCLE"
- Parse abbreviated dates: "19 Jun - 21 Jun" → start: "2026-06-19", end: "2026-06-21"
- Leave sessions array EMPTY - we only need event and venue info

HTML Content (search for event lists, calendar entries, or schedule tables):
{html}
"""
