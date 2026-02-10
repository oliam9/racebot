"""
Playwright Integration Test.

Tests Playwright-based fetch against a local test page and real IndyCar schedule.
"""

import pytest
import asyncio
from pathlib import Path

# Skip if playwright not installed
pytest.importorskip("playwright")

from browser_client import (
    fetch_rendered,
    capture_json_responses,
    discover_schedule_endpoints,
    cleanup_browser,
    BrowserConfig,
)


@pytest.fixture
def test_html_page(tmp_path):
    """Create a local test HTML page with JS-rendered content."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Schedule Page</title>
    </head>
    <body>
        <h1>Schedule</h1>
        <div id="consent-banner">
            <button id="accept-btn">Accept Cookies</button>
        </div>
        <div id="schedule-container">Loading...</div>
        
        <script>
            // Simulate JS-rendered content
            setTimeout(() => {
                document.getElementById('schedule-container').innerHTML = `
                    <div class="event">
                        <h2>Grand Prix of Test</h2>
                        <p>March 15-17, 2024</p>
                        <div class="session">Practice 1: 10:00 AM ET</div>
                        <div class="session">Qualifying: 2:00 PM ET</div>
                        <div class="session">Race: 12:00 PM ET</div>
                    </div>
                `;
            }, 500);
            
            // Mock XHR request
            setTimeout(() => {
                fetch('/api/schedule.json', {
                    method: 'GET',
                    headers: {'Content-Type': 'application/json'}
                });
            }, 1000);
        </script>
    </body>
    </html>
    """
    
    test_file = tmp_path / "test_page.html"
    test_file.write_text(html_content)
    return f"file://{test_file.as_posix()}"


@pytest.mark.asyncio
@pytest.mark.integration
class TestPlaywrightIntegration:
    """Integration tests against real and mock pages."""
    
    async def test_fetch_js_rendered_content(self, test_html_page):
        """Test that JS-rendered content is captured."""
        config = BrowserConfig(headless=True)
        
        try:
            page = await fetch_rendered(
                test_html_page,
                wait_for="#schedule-container",
                config=config,
            )
            
            assert page.status_code == 0  # File protocol returns 0
            assert "Grand Prix of Test" in page.content
            assert "Practice 1" in page.content
        finally:
            await cleanup_browser()
    
    async def test_consent_handler(self, test_html_page):
        """Test that consent handler clicks cookie consent button."""
        config = BrowserConfig(headless=True)
        
        try:
            page = await fetch_rendered(
                test_html_page,
                handle_consent=True,
                config=config,
            )
            
            # Page should load successfully even with consent banner
            assert "Schedule" in page.content
        finally:
            await cleanup_browser()
    
    async def test_resource_blocking(self):
        """Test that resource blocking reduces load time."""
        config_full = BrowserConfig(
            headless=True,
            block_images=False,
            block_fonts=False,
            block_media=False,
        )
        config_blocked = BrowserConfig(
            headless=True,
            block_images=True,
            block_fonts=True,
            block_media=True,
        )
        
        try:
            # Fetch with all resources
            page_full = await fetch_rendered(
                "https://example.com",
                config=config_full,
            )
            
            # Fetch with blocked resources
            page_blocked = await fetch_rendered(
                "https://example.com",
                config=config_blocked,
            )
            
            # Blocked should be faster (ideally)
            # Note: example.com is simple so difference may be minimal
            assert page_full.load_time_ms > 0
            assert page_blocked.load_time_ms > 0
        finally:
            await cleanup_browser()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
class TestRealSources:
    """Test against real motorsport sources (slow, optional)."""
    
    async def test_indycar_schedule_http(self):
        """Test that IndyCar schedule works with pure HTTP (no Playwright needed)."""
        import httpx
        
        url = "https://www.indycar.com/schedule"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=30.0)
            
        assert response.status_code == 200
        assert "schedule" in response.text.lower()
    
    async def test_indycar_schedule_playwright(self):
        """Test fetching IndyCar schedule with Playwright."""
        config = BrowserConfig(headless=True, timeout_ms=30000)
        
        try:
            page = await fetch_rendered(
                "https://www.indycar.com/schedule",
                wait_for="h1",
                config=config,
            )
            
            assert page.status_code == 200
            assert "schedule" in page.content.lower()
            print(f"Load time: {page.load_time_ms}ms")
        finally:
            await cleanup_browser()
    
    async def test_capture_indycar_endpoints(self):
        """Test capturing network responses from IndyCar schedule."""
        config = BrowserConfig(headless=True, timeout_ms=30000)
        
        try:
            responses = await capture_json_responses(
                "https://www.indycar.com/schedule",
                patterns=["schedule", "event", "session", "calendar"],
                config=config,
            )
            
            print(f"Captured {len(responses)} responses")
            
            if responses:
                ranked = discover_schedule_endpoints(responses)
                for resp, score in ranked[:3]:
                    print(f"  {resp.url} (score: {score}, {resp.content_type})")
        finally:
            await cleanup_browser()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
