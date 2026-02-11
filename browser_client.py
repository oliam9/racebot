"""
Browser Client — Playwright-based browser automation for JS-rendered pages.

Provides:
  - Browser pool management (single instance, context pooling)
  - Network request interception and capture
  - Resource blocking (images, fonts, media, trackers)
  - Generic consent handler for cookie banners
  - Retry logic with exponential backoff
  - Timeout management

Usage:
    # Fetch a rendered page
    page = await fetch_rendered("https://example.com/schedule")
    
    # Capture JSON responses
    responses = await capture_json_responses(
        "https://example.com/schedule",
        patterns=["schedule", "calendar", "session"]
    )
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from contextlib import asynccontextmanager

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Response,
    Route,
    Request,
)


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

@dataclass
class BrowserConfig:
    """Browser client configuration."""
    
    enabled: bool = True
    browser_type: str = "chromium"  # chromium | firefox | webkit
    headless: bool = True
    max_concurrent_pages: int = 3
    timeout_ms: int = 45000
    navigation_timeout_ms: int = 30000
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    locale: str = "en-US"
    
    # Resource blocking
    block_images: bool = True
    block_fonts: bool = True
    block_media: bool = True
    block_trackers: bool = True
    
    # Retry configuration
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    
    @classmethod
    def from_env(cls) -> BrowserConfig:
        """Load configuration from environment variables."""
        return cls(
            enabled=os.getenv("PLAYWRIGHT_ENABLED", "true").lower() == "true",
            browser_type=os.getenv("PLAYWRIGHT_BROWSER", "chromium"),
            headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true",
            max_concurrent_pages=int(os.getenv("PLAYWRIGHT_MAX_PAGES", "3")),
            timeout_ms=int(os.getenv("PLAYWRIGHT_TIMEOUT", "45000")),
        )


# ------------------------------------------------------------------
# Data models
# ------------------------------------------------------------------

@dataclass
class RenderedPage:
    """Result of fetching a rendered page."""
    
    url: str
    content: str  # HTML content
    status_code: int
    retrieved_at: datetime
    load_time_ms: float
    method: str = "playwright_dom"  # extraction method
    metadata: Dict[str, any] = field(default_factory=dict)


@dataclass
class CapturedResponse:
    """Captured network response."""
    
    url: str
    method: str  # GET, POST, etc.
    status_code: int
    content_type: str
    body: str  # Response body (if JSON/text)
    headers: Dict[str, str]
    timestamp: datetime
    
    def is_json(self) -> bool:
        """Check if response is JSON."""
        return "application/json" in self.content_type.lower()
    
    def is_calendar(self) -> bool:
        """Check if response is iCalendar."""
        return "text/calendar" in self.content_type.lower()


# ------------------------------------------------------------------
# Browser Pool — singleton instance manager
# ------------------------------------------------------------------

class BrowserPool:
    """
    Manages a single browser instance with context pooling.
    
    Thread-safe singleton pattern for resource efficiency.
    Handles event loop changes by reinitializing when necessary.
    """
    
    _instances: Dict[asyncio.AbstractEventLoop, 'BrowserPool'] = {}
    
    def __init__(self, config: BrowserConfig):
        self.config = config
        self._browser: Optional[Browser] = None
        self._playwright = None
        self._contexts: List[BrowserContext] = []
        self._semaphore = asyncio.Semaphore(config.max_concurrent_pages)
        self._rate_limiters: Dict[str, float] = {}  # domain -> last_request_time
        
    @classmethod
    async def get_instance(cls, config: Optional[BrowserConfig] = None) -> 'BrowserPool':
        """Get or create singleton instance for the current event loop."""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("BrowserPool must be used within a running event loop")
        
        # Clean up closed loops from registry
        # Create a list of keys to remove to avoid runtime error during iteration
        for loop in list(cls._instances.keys()):
            if loop.is_closed():
                # We can't await close() here because the loop is closed
                # Just remove from registry
                cls._instances.pop(loop, None)
        
        if current_loop not in cls._instances:
            cfg = config or BrowserConfig.from_env()
            instance = BrowserPool(cfg)
            await instance._initialize()
            cls._instances[current_loop] = instance
        
        return cls._instances[current_loop]
    
    async def _initialize(self):
        """Initialize browser instance."""
        if not self.config.enabled:
            return
        
        self._playwright = await async_playwright().start()
        
        # Select browser type
        if self.config.browser_type == "firefox":
            browser_type = self._playwright.firefox
        elif self.config.browser_type == "webkit":
            browser_type = self._playwright.webkit
        else:
            browser_type = self._playwright.chromium
        
        self._browser = await browser_type.launch(
            headless=self.config.headless,
        )
    
    async def close(self):
        """Close browser and cleanup."""
        for ctx in self._contexts:
            try:
                await ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
    
    @classmethod
    async def close_all(cls):
        """Close all browser instances in all loops (that are still running)."""
        # This is tricky because we can't easily await things in other loops.
        # Ideally, this is called when the application shuts down.
        # We will try to close the instance for the CURRENT loop.
        try:
            current_loop = asyncio.get_running_loop()
            if current_loop in cls._instances:
                await cls._instances[current_loop].close()
                del cls._instances[current_loop]
        except RuntimeError:
            pass
            
        # For other loops, we can't do much if we are not in them.
        # They should rely on their own cleanup or garbage collection.
    
    @asynccontextmanager
    async def get_page(self):
        """Get a page from the pool (context manager)."""
        if not self.config.enabled or not self._browser:
            raise RuntimeError("Browser not initialized or disabled")
        
        async with self._semaphore:
            # Create new context
            context = await self._browser.new_context(
                user_agent=self.config.user_agent,
                locale=self.config.locale,
                viewport={"width": 1920, "height": 1080},
            )
            context.set_default_timeout(self.config.timeout_ms)
            context.set_default_navigation_timeout(self.config.navigation_timeout_ms)
            
            self._contexts.append(context)
            page = await context.new_page()
            
            try:
                yield page
            finally:
                await page.close()
                await context.close()
                self._contexts.remove(context)
    
    async def rate_limit(self, url: str, delay: float = 1.0):
        """Enforce per-domain rate limiting."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        
        last_request = self._rate_limiters.get(domain, 0)
        elapsed = time.time() - last_request
        
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)
        
        self._rate_limiters[domain] = time.time()


# ------------------------------------------------------------------
# Resource blocking
# ------------------------------------------------------------------

BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
TRACKER_DOMAINS = {
    "google-analytics.com",
    "googletagmanager.com",
    "facebook.com",
    "twitter.com",
    "doubleclick.net",
    "analytics.google.com",
    "hotjar.com",
    "mixpanel.com",
    "segment.com",
}


async def _block_resources(route: Route, request: Request, config: BrowserConfig):
    """Route handler to block unwanted resources."""
    resource_type = request.resource_type
    url = request.url.lower()
    
    # Block by resource type
    if config.block_images and resource_type == "image":
        await route.abort()
        return
    if config.block_fonts and resource_type == "font":
        await route.abort()
        return
    if config.block_media and resource_type == "media":
        await route.abort()
        return
    
    # Block trackers
    if config.block_trackers:
        for tracker in TRACKER_DOMAINS:
            if tracker in url:
                await route.abort()
                return
    
    await route.continue_()


# ------------------------------------------------------------------
# Consent handler
# ------------------------------------------------------------------

CONSENT_BUTTON_PATTERNS = [
    "accept",
    "agree",
    "consent",
    "allow",
    "ok",
    "continue",
    "i agree",
    "accept all",
    "allow all",
]


async def _handle_consent(page: Page) -> bool:
    """
    Try to dismiss cookie consent banners.
    
    Returns True if consent button found and clicked.
    """
    for pattern in CONSENT_BUTTON_PATTERNS:
        try:
            # Look for buttons/links with consent-like text
            selector = f"button:has-text('{pattern}'), a:has-text('{pattern}')"
            button = page.locator(selector).first
            
            if await button.count() > 0:
                await button.click(timeout=2000)
                await page.wait_for_timeout(500)  # Wait for potential redirect
                return True
        except Exception:
            continue
    
    return False


# ------------------------------------------------------------------
# Main API functions
# ------------------------------------------------------------------

async def fetch_rendered(
    url: str,
    *,
    wait_for: Optional[str] = None,
    timeout_ms: Optional[int] = None,
    handle_consent: bool = True,
    config: Optional[BrowserConfig] = None,
) -> RenderedPage:
    """
    Fetch a page with browser rendering.
    
    Args:
        url: URL to fetch
        wait_for: CSS selector to wait for (optional)
        timeout_ms: Override default timeout
        handle_consent: Try to dismiss cookie banners
        config: Browser configuration (uses env defaults if None)
    
    Returns:
        RenderedPage with content and metadata
    
    Raises:
        RuntimeError: If browser disabled or page load fails
    """
    cfg = config or BrowserConfig.from_env()
    pool = await BrowserPool.get_instance(cfg)
    
    await pool.rate_limit(url)
    
    start_time = time.time()
    
    async with pool.get_page() as page:
        # Set up resource blocking
        await page.route("**/*", lambda route, request: _block_resources(route, request, cfg))
        
        # Navigate
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=timeout_ms or cfg.navigation_timeout_ms,
        )
        
        # Wait for network idle (best effort, don't fail if timeout)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        
        # Handle consent if enabled
        if handle_consent:
            await _handle_consent(page)
        
        # Wait for specific selector if provided
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=timeout_ms or cfg.timeout_ms)
        
        # Get content
        content = await page.content()
        status_code = response.status if response else 0
        
        load_time_ms = (time.time() - start_time) * 1000
        
        return RenderedPage(
            url=url,
            content=content,
            status_code=status_code,
            retrieved_at=datetime.utcnow(),
            load_time_ms=load_time_ms,
            method="playwright_dom",
        )


async def capture_json_responses(
    url: str,
    *,
    patterns: Optional[List[str]] = None,
    timeout_ms: Optional[int] = None,
    handle_consent: bool = True,
    config: Optional[BrowserConfig] = None,
) -> List[CapturedResponse]:
    """
    Capture network responses matching patterns.
    
    Args:
        url: Page URL to load
        patterns: URL patterns to capture (e.g., ["schedule", "calendar"])
        timeout_ms: Override default timeout
        handle_consent: Try to dismiss cookie banners
        config: Browser configuration
    
    Returns:
        List of captured responses
    """
    cfg = config or BrowserConfig.from_env()
    pool = await BrowserPool.get_instance(cfg)
    
    await pool.rate_limit(url)
    
    patterns = patterns or []
    captured: List[CapturedResponse] = []
    
    async def response_handler(response: Response):
        """Capture matching responses."""
        resp_url = response.url.lower()
        
        # Check if URL matches any pattern
        matches = not patterns or any(p.lower() in resp_url for p in patterns)
        
        if matches and response.ok:
            content_type = response.headers.get("content-type", "")
            
            # Only capture JSON, calendar, or text responses
            if any(t in content_type.lower() for t in ["json", "calendar", "text"]):
                try:
                    body = await response.text()
                    
                    captured.append(
                        CapturedResponse(
                            url=response.url,
                            method=response.request.method,
                            status_code=response.status,
                            content_type=content_type,
                            body=body,
                            headers=dict(response.headers),
                            timestamp=datetime.utcnow(),
                        )
                    )
                except Exception:
                    pass
    
    async with pool.get_page() as page:
        # Set up response handler
        page.on("response", response_handler)
        
        # Set up resource blocking
        await page.route("**/*", lambda route, request: _block_resources(route, request, cfg))
        
        # Navigate and wait
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=timeout_ms or cfg.navigation_timeout_ms,
        )
        
        # Wait for network to settle
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        
        # Handle consent
        if handle_consent:
            await _handle_consent(page)
        
        # Additional wait to catch late XHR requests
        await page.wait_for_timeout(2000)
    
    return captured


async def fetch_rendered_with_retry(
    url: str,
    max_retries: Optional[int] = None,
    **kwargs,
) -> RenderedPage:
    """
    Fetch rendered page with retry logic.
    
    On retry, disables images/fonts for faster loading.
    """
    config = kwargs.get("config") or BrowserConfig.from_env()
    retries = max_retries or config.max_retries
    
    for attempt in range(retries):
        try:
            # On retry, force resource blocking
            if attempt > 0:
                retry_config = BrowserConfig.from_env()
                retry_config.block_images = True
                retry_config.block_fonts = True
                retry_config.block_media = True
                kwargs["config"] = retry_config
            
            return await fetch_rendered(url, **kwargs)
        
        except Exception as e:
            if attempt == retries - 1:
                raise
            
            wait_time = config.retry_backoff_base ** attempt
            await asyncio.sleep(wait_time)
    
    raise RuntimeError(f"Failed to fetch {url} after {retries} attempts")


# ------------------------------------------------------------------
# Endpoint discovery heuristics
# ------------------------------------------------------------------

def discover_schedule_endpoints(
    responses: List[CapturedResponse],
) -> List[Tuple[CapturedResponse, float]]:
    """
    Rank captured responses by likelihood of being schedule data.
    
    Returns list of (response, confidence_score) tuples, sorted by score.
    """
    scored: List[Tuple[CapturedResponse, float]] = []
    
    SCHEDULE_KEYWORDS = {
        "schedule": 3.0,
        "calendar": 3.0,
        "timetable": 3.0,
        "session": 2.5,
        "event": 2.0,
        "race": 1.5,
        "practice": 1.5,
        "qualifying": 1.5,
    }
    
    for resp in responses:
        score = 0.0
        url_lower = resp.url.lower()
        
        # URL contains schedule keywords
        for keyword, weight in SCHEDULE_KEYWORDS.items():
            if keyword in url_lower:
                score += weight
        
        # Content type scoring
        if resp.is_json():
            score += 2.0
        elif resp.is_calendar():
            score += 5.0  # ICS feeds are gold
        
        # URL pattern scoring
        if "/api/" in url_lower:
            score += 1.5
        if "/v1/" in url_lower or "/v2/" in url_lower:
            score += 1.0
        
        # Body analysis (if JSON)
        if resp.is_json() and resp.body:
            body_lower = resp.body.lower()
            for keyword in ["start", "end", "session", "event", "date", "time"]:
                if keyword in body_lower:
                    score += 0.5
        
        if score > 0:
            scored.append((resp, score))
    
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# ------------------------------------------------------------------
# Cleanup
# ------------------------------------------------------------------

async def cleanup_browser():
    """Close the global browser instance."""
    await BrowserPool.close_all()
