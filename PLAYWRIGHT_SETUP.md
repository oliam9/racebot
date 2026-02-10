# Playwright Browser Automation Setup

## Installation

1. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Playwright browsers**:
   ```bash
   playwright install chromium
   ```
   
   Or install all browsers:
   ```bash
   playwright install
   ```

3. **System Dependencies** (Linux/WSL):
   ```bash
   playwright install-deps
   ```

## Configuration

Playwright is **disabled by default**. Enable it with environment variable:

```bash
export PLAYWRIGHT_ENABLED=true
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PLAYWRIGHT_ENABLED` | `false` | Enable/disable Playwright browser automation |
| `PLAYWRIGHT_BROWSER` | `chromium` | Browser type: `chromium`, `firefox`, or `webkit` |
| `PLAYWRIGHT_HEADLESS` | `true` | Run browser in headless mode |
| `PLAYWRIGHT_MAX_PAGES` | `3` | Maximum concurrent browser pages |
| `PLAYWRIGHT_TIMEOUT` | `45000` | Page load timeout in milliseconds |

### Example `.env` file:

```env
PLAYWRIGHT_ENABLED=true
PLAYWRIGHT_BROWSER=chromium
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_MAX_PAGES=3
```

## Usage

### In Connectors

Connectors can use Playwright optionally:

```python
from connectors.base import Connector

class MyConnector(Connector):
    def fetch_season(self, series_id: str, season: int):
        url = "https://example.com/schedule"
        
        # Try HTTP first
        try:
            response = self._http_get(url)
            return self._parse_http_response(response)
        except Exception:
            pass
        
        # Fallback to Playwright if enabled
        if self.playwright_enabled:
            # Capture JSON endpoints
            endpoints = self._run_async(
                self._capture_endpoints(
                    url,
                    patterns=["schedule", "session", "event"]
                )
            )
            
            if endpoints:
                # Use discovered endpoint
                return self._fetch_from_endpoint(endpoints[0].url)
            
            # Or render page DOM
            page = self._run_async(
                self._playwright_get(url, wait_for=".schedule-table")
            )
            return self._parse_rendered_page(page)
```

### Direct API Usage

```python
import asyncio
from browser_client import fetch_rendered, capture_json_responses

async def main():
    # Fetch rendered page
    page = await fetch_rendered(
        "https://example.com/schedule",
        wait_for=".schedule-container",
    )
    print(f"Status: {page.status_code}")
    print(f"Content length: {len(page.content)}")
    
    # Capture network responses
    responses = await capture_json_responses(
        "https://example.com/schedule",
        patterns=["schedule", "calendar"],
    )
    
    for resp in responses:
        if resp.is_json():
            print(f"Found JSON endpoint: {resp.url}")

asyncio.run(main())
```

## Network-First Strategy

The system follows a "network-first, DOM-second" approach:

1. **Attempt HTTP first** using `httpx` for speed and reliability
2. **Use Playwright only when needed**:
   - Page requires JavaScript to render schedule content
   - Schedule is loaded via XHR/fetch (discoverable endpoints)
3. **Capture network requests** to detect JSON/ICS endpoints
4. **Graduate discovered endpoints** to direct HTTP access

### Example Flow

```
┌─────────────────┐
│  Try HTTP GET   │
│   (httpx)       │
└────────┬────────┘
         │
         ├─ Success → Parse & Return
         │
         ├─ Fail/No Data
         │
         ▼
┌─────────────────┐
│ Try Playwright  │
│ (if enabled)    │
└────────┬────────┘
         │
         ├─ Capture network requests
         │  └─ Find JSON endpoints
         │     └─ Use endpoint directly (cache for future)
         │
         └─ Render DOM
            └─ Extract from HTML
```

## Features

### Resource Blocking
Playwright automatically blocks:
- Images (unless needed)
- Fonts (unless needed)
- Media files (video/audio)
- Tracking scripts

This reduces bandwidth and improves load times by 30-50%.

### Consent Handling
Generic consent handler automatically clicks:
- "Accept" / "Accept All"
- "I Agree"
- "Allow Cookies"
- "Continue"

### Retry Logic
Automatic retry with exponential backoff:
- Default: 3 attempts
- Backoff: 2^attempt seconds
- On retry: enables aggressive resource blocking

### Rate Limiting
Per-domain rate limiting:
- Default: 1 second between requests to same domain
- Prevents overwhelming servers
- Configurable per connector

## Testing

Run tests:

```bash
# All tests
pytest tests/

# Unit tests only
pytest tests/test_browser_client.py

# Integration tests (requires network)
pytest tests/test_playwright_integration.py -m integration

# Acceptance test (no Selenium)
pytest tests/test_no_selenium.py
```

Mark slow tests:
```bash
pytest -m "not slow"
```

## Deployment

### Docker

Add to Dockerfile:
```dockerfile
RUN pip install -r requirements.txt
RUN playwright install --with-deps chromium
```

### Server Requirements

Playwright requires system libraries for headless browser:
- **Ubuntu/Debian**: `playwright install-deps` handles it
- **Alpine**: Use `microsoft/playwright:python` base image
- **Windows**: No additional deps needed

### Production Recommendations

1. **Disable by default**: Set `PLAYWRIGHT_ENABLED=false`
2. **Enable per-connector**: Let specific connectors opt-in
3. **Resource limits**: Use Docker memory limits (recommended: 2GB+ for browser)
4. **Monitoring**: Track browser pool metrics and page load times

## Troubleshooting

### "playwright not installed"
```bash
pip install 'playwright>=1.40.0'
playwright install chromium
```

### "Browser closed unexpectedly"
- Increase memory limits (Docker/container)
- Check system dependencies: `playwright install-deps`

### "Timeout waiting for selector"
- Increase `PLAYWRIGHT_TIMEOUT`
- Check if selector exists on page
- Try waiting for different selector

### Slow page loads
- Enable resource blocking (default)
- Reduce `PLAYWRIGHT_MAX_PAGES`
- Use discovered endpoints instead of DOM scraping

## Performance Tips

1. **Graduate to HTTP**: Once you discover a JSON endpoint, cache it and use HTTP directly
2. **Selective Playwright**: Only use for pages that truly need JS rendering
3. **Parallel limits**: Keep `PLAYWRIGHT_MAX_PAGES` low (2-3) to avoid memory issues
4. **Resource blocking**: Always enabled for non-essential resources

## Architecture

```
browser_client.py
├── BrowserPool (singleton)
│   ├── Browser instance management
│   ├── Context pooling
│   └── Rate limiting
│
├── fetch_rendered()
│   └── Fetch JS-rendered pages
│
├── capture_json_responses()
│   └── Intercept network requests
│
└── discover_schedule_endpoints()
    └── Rank discovered endpoints
```

## See Also

- [Implementation Plan](./implementation_plan.md)
- [Playwright Documentation](https://playwright.dev/python/)
