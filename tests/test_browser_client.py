"""
Unit tests for browser_client module.

Tests browser pool, network capture, resource blocking, and retry logic.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock

# Skip all tests if playwright not installed
pytest.importorskip("playwright")

from browser_client import (
    BrowserConfig,
    BrowserPool,
    RenderedPage,
    CapturedResponse,
    fetch_rendered,
    capture_json_responses,
    fetch_rendered_with_retry,
    discover_schedule_endpoints,
    cleanup_browser,
)


class TestBrowserConfig:
    """Test browser configuration."""
    
    def test_default_config(self):
        """Test default configuration"""
        config = BrowserConfig()
        assert config.enabled == True
        assert config.browser_type == "chromium"
        assert config.headless == True
        assert config.max_concurrent_pages == 3
    
    def test_from_env(self, monkeypatch):
        """Test loading from environment variables."""
        monkeypatch.setenv("PLAYWRIGHT_ENABLED", "false")
        monkeypatch.setenv("PLAYWRIGHT_BROWSER", "firefox")
        monkeypatch.setenv("PLAYWRIGHT_MAX_PAGES", "5")
        
        config = BrowserConfig.from_env()
        assert config.enabled == False
        assert config.browser_type == "firefox"
        assert config.max_concurrent_pages == 5


class TestCapturedResponse:
    """Test CapturedResponse dataclass."""
    
    def test_is_json(self):
        """Test JSON detection."""
        resp = CapturedResponse(
            url="https://example.com/api/schedule",
            method="GET",
            status_code=200,
            content_type="application/json; charset=utf-8",
            body='{"events": []}',
            headers={},
            timestamp=datetime.utcnow(),
        )
        assert resp.is_json() == True
    
    def test_is_calendar(self):
        """Test calendar detection."""
        resp = CapturedResponse(
            url="https://example.com/schedule.ics",
            method="GET",
            status_code=200,
            content_type="text/calendar",
            body="BEGIN:VCALENDAR",
            headers={},
            timestamp=datetime.utcnow(),
        )
        assert resp.is_calendar() == True


class TestDiscoverScheduleEndpoints:
    """Test endpoint discovery heuristics."""
    
    def test_ranks_json_schedule_high(self):
        """Test that JSON schedule endpoints score highest."""
        responses = [
            CapturedResponse(
                url="https://example.com/api/v1/schedule",
                method="GET",
                status_code=200,
                content_type="application/json",
                body='{"events": [{"start": "2024-01-01"}]}',
                headers={},
                timestamp=datetime.utcnow(),
            ),
            CapturedResponse(
                url="https://example.com/tracker.js",
                method="GET",
                status_code=200,
                content_type="text/javascript",
                body="console.log('hi')",
                headers={},
                timestamp=datetime.utcnow(),
            ),
        ]
        
        ranked = discover_schedule_endpoints(responses)
        assert len(ranked) > 0
        assert "schedule" in ranked[0][0].url
        assert ranked[0][1] > 5.0  # High confidence score
    
    def test_calendar_scores_highest(self):
        """Test that ICS calendar files score highest."""
        responses = [
            CapturedResponse(
                url="https://example.com/schedule.ics",
                method="GET",
                status_code=200,
                content_type=" text/calendar",
                body="BEGIN:VCALENDAR",
                headers={},
                timestamp=datetime.utcnow(),
            ),
        ]
        
        ranked = discover_schedule_endpoints(responses)
        assert ranked[0][1] >= 8.0  # Calendar + schedule keyword


@pytest.mark.asyncio
class TestBrowserPool:
    """Test browser pool management."""
    
    async def test_singleton_pattern(self):
        """Test that BrowserPool is a singleton."""
        config = BrowserConfig(enabled=False)  # Disabled to avoid launching browser
        pool1 = await BrowserPool.get_instance(config)
        pool2 = await BrowserPool.get_instance()
        
        assert pool1 is pool2
        
        await cleanup_browser()
    
    async def test_rate_limiting(self):
        """Test per-domain rate limiting."""
        config = BrowserConfig(enabled=False)
        pool = await BrowserPool.get_instance(config)
        
        url1 = "https://example.com/page1"
        url2 = "https://example.com/page2"
        
        start = asyncio.get_event_loop().time()
        await pool.rate_limit(url1, delay=0.5)
        await pool.rate_limit(url2, delay=0.5)  # Same domain
        elapsed = asyncio.get_event_loop().time() - start
        
        assert elapsed >= 0.5  # Should have delayed
        
        await cleanup_browser()


@pytest.mark.asyncio
@pytest.mark.integration
class TestFetchRendered:
    """Integration tests for fetch_rendered (requires network)."""
    
    async def test_fetch_simple_page(self):
        """Test fetching a simple HTML page."""
        # Use a reliable test page
        config = BrowserConfig(headless=True, timeout_ms=15000)
        
        try:
            page = await fetch_rendered(
                "https://example.com",
                config=config,
            )
            
            assert page.status_code == 200
            assert "Example Domain" in page.content
            assert page.method == "playwright_dom"
            assert page.load_time_ms > 0
        finally:
            await cleanup_browser()
    
    async def test_wait_for_selector(self):
        """Test waiting for specific selector."""
        config = BrowserConfig(headless=True)
        
        try:
            page = await fetch_rendered(
                "https://example.com",
                wait_for="h1",
                config=config,
            )
            
            assert "Example" in page.content
        finally:
            await cleanup_browser()


@pytest.mark.asyncio
@pytest.mark.integration
class TestCaptureJsonResponses:
    """Integration tests for network capture."""
    
    async def test_capture_with_patterns(self):
        """Test capturing responses matching patterns."""
        # This test requires a real page loading JSON
        # For now, just test the API works
        config = BrowserConfig(headless=True, timeout_ms=10000)
        
        try:
            responses = await capture_json_responses(
                "https://example.com",
                patterns=["example"],
                config=config,
            )
            
            # May or may not capture anything from example.com
            assert isinstance(responses, list)
        finally:
            await cleanup_browser()


@pytest.mark.asyncio
class TestFetchRenderedWithRetry:
    """Test retry logic."""
    
    async def test_retries_on_failure(self):
        """Test that fetch retries on transient failures."""
        config = BrowserConfig(enabled=False)
        
        with patch('browser_client.fetch_rendered', side_effect=[
            Exception("Timeout"),
            Exception("Timeout"),
            RenderedPage(
                url="https://example.com",
                content="<html></html>",
                status_code=200,
                retrieved_at=datetime.utcnow(),
                load_time_ms=100,
            )
        ]):
            # Should succeed on third attempt
            page = await fetch_rendered_with_retry(
                "https://example.com",
                max_retries=3,
                config=config,
            )
            
            assert page.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
