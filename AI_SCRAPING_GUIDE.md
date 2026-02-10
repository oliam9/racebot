# AI-Powered Web Scraping Setup Guide

## Overview

The Search Discovery feature now supports two modes:
1. **Web Search (API)** - Automatically find schedule pages using Google/Bing search APIs
2. **Direct URL Scraping** - Extract data from a specific URL using AI (Anthropic Claude or Google Gemini)

## Quick Setup

### 1. Install Required Packages

```bash
# For Anthropic Claude
pip install anthropic

# For Google Gemini (already installed)
pip install google-generativeai

# Already installed via requirements.txt:
# - httpx
# - playwright
# - beautifulsoup4
# - selectolax
```

### 2. Get API Keys

#### Option A: Anthropic Claude (Recommended for Complex Pages)

1. Visit: https://console.anthropic.com
2. Sign up for an account (get $5 free credit)
3. Go to API Keys section
4. Create a new API key
5. Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-api...`

**Pricing:**
- $3 per 1M input tokens (~750,000 words)
- $15 per 1M output tokens (~750,000 words)
- **Typical schedule page**: ~$0.01-0.05 per extraction

**Rate Limits:**
- Default: 1,000 requests/minute
- You're limited by our 3 requests/minute safety limit

#### Option B: Google Gemini (Best for Cost-Effective Bulk)

1. Visit: https://makersuite.google.com/app/apikey
2. Sign in with Google account
3. Click "Create API Key"
4. Add to `.env`: `GEMINI_API_KEY=AIza...`

**Pricing:**
- **FREE TIER**: 60 requests/minute
- Flash model: Free up to 15 RPM, then ~$0.075 per 1M tokens
- **Typical schedule page**: FREE for most use cases

**Rate Limits:**
- Free tier: 15 requests/minute
- Paid tier: 360 requests/minute
- You're limited by our 3 requests/minute safety limit

### 3. Configure Environment

Copy `.env.example` to `.env` and add your keys:

```env
# Choose your AI provider
ANTHROPIC_API_KEY=sk-ant-api03-...
GEMINI_API_KEY=AIza...

# Browser automation (recommended)
PLAYWRIGHT_ENABLED=true
```

## Safety Features

### Rate Limiting
- **Default**: 3 requests per minute per domain
- Prevents server overload and detection
- Automatic delays between requests
- Per-domain tracking

### Caching
- **24-hour cache** for scraped pages
- Avoids redundant requests
- Stored in `.cache/scraper/` directory
- Automatically expires old content

### Respectful Scraping
- User-Agent identification: `MotorsportBot/1.0 (Schedule Data Collector; Educational Use)`
- Minimum 20-second delays between requests to same domain
- Playwright for JavaScript-heavy sites (respects page load)
- No concurrent requests to same domain

### Error Handling
- Exponential backoff on failures
- Graceful degradation (Playwright → httpx fallback)
- Detailed error messages
- Warning collection for partial extraction

## Usage in the App

### Web Search Mode (existing feature)

```
1. Navigate to "Search Discovery" tab
2. Select "🌐 Web Search (API)" mode
3. Choose a series (e.g., "IMSA WeatherTech")
4. Enter season year
5. Click "🔎 Search"
```

### Direct URL Scraping Mode (NEW)

```
1. Navigate to "Search Discovery" tab
2. Select "📄 Direct URL Scraping" mode
3. Choose a series
4. Enter season year
5. Paste schedule page URL (e.g., https://www.fia.com/wec/calendar)
6. Select AI Provider (Anthropic Claude or Google Gemini)
7. Click "🤖 Extract Data"
```

**Best URLs to scrape:**
- Official championship schedule pages
- Calendar pages with event listings
- Pages with session times
- Avoid: News articles, individual event pages

**Examples:**
- Formula 1: https://www.formula1.com/en/racing/2026.html
- MotoGP: https://www.motogp.com/en/calendar
- IMSA: https://www.imsa.com/weathertech/schedule/
- WEC: https://www.fia.com/wec/calendar

## Cost Estimates

### Anthropic Claude
| Operation | Input Tokens | Output Tokens | Cost |
|-----------|--------------|---------------|------|
| Small schedule (5 events) | ~10k | ~2k | ~$0.06 |
| Medium schedule (15 events) | ~30k | ~5k | ~$0.17 |
| Large schedule (25 events) | ~50k | ~8k | ~$0.27 |

### Google Gemini
| Operation | Input Tokens | Output Tokens | Cost |
|-----------|--------------|---------------|------|
| Any schedule | Any | Any | **FREE** |
| (Free tier limit: 15 RPM) | | | |

## Best Practices

### 1. When to Use Direct URL Scraping
✅ **Good use cases:**
- Official championship websites
- Dedicated schedule/calendar pages
- When connectors don't exist
- Testing new series support

❌ **Avoid:**
- News articles or blogs
- Social media posts
- Individual race event pages
- Unofficial fan sites

### 2. Choosing AI Provider

**Use Anthropic Claude when:**
- Page structure is complex
- Tables and nested content
- Need highest accuracy
- Budget allows (~$0.10 per schedule)

**Use Google Gemini when:**
- Processing multiple schedules
- Testing/development
- Clean, simple page structures
- Cost is primary concern (FREE)

### 3. Preventing Blocks

Our safety features already handle this, but additional tips:

1. **Don't spam**: Wait for results before trying again
2. **Use official sites**: Better structured, more reliable
3. **Cache is your friend**: Re-running uses cache (24hrs)
4. **One schedule at a time**: No parallel scraping
5. **Check robots.txt**: Most championship sites allow bots

### 4. Troubleshooting

**"API key not found"**
- Check `.env` file exists in project root
- Verify key name: `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`
- Restart Streamlit app after adding keys

**"Rate limit exceeded"**
- Wait 1 minute before trying again
- Check if you're hitting API provider limits
- Our scraper enforces 3 req/min automatically

**"Extraction failed"**
- Verify URL is accessible in browser
- Check if page requires login
- Try different AI provider
- Page might be too dynamic (needs Playwright)

**"No events found"**
- URL might not be a schedule page
- Try official calendar URL
- Check if AI needs clearer page structure
- Verify season year matches page content

## Advanced Configuration

### Adjusting Rate Limits

Edit `search/ai_scraper.py`:

```python
# Default: 3 requests per minute
scraper = AIScraper(
    ai_provider="anthropic claude",
    requests_per_minute=2,  # More conservative
    cache_hours=48,          # Longer cache
)
```

### Custom Cache Location

```python
cache = ResponseCache(cache_dir="./my_cache")
```

### Clearing Cache

```bash
# Remove all cached pages
rm -rf .cache/scraper/

# On Windows PowerShell
Remove-Item -Recurse -Force .cache/scraper/
```

## API Limits Summary

| Provider | Free Tier | Rate Limit | Cost/1M tokens |
|----------|-----------|------------|----------------|
| **Anthropic Claude** | $5 credit | 1,000 RPM | $3 input, $15 output |
| **Google Gemini** | 60 RPM free | 15-60 RPM | FREE (flash model) |
| **Our Scraper** | N/A | **3 RPM** | N/A |

## Security Notes

### What We DO:
✅ Load API keys from environment only
✅ Never display or log API keys
✅ Respect rate limits automatically
✅ Cache responses to minimize requests
✅ Use conservative delays
✅ Identify our bot clearly

### What We DON'T DO:
❌ Store API keys in code
❌ Make requests without rate limiting
❌ Scrape without user-agent
❌ Bypass authentication
❌ Violate terms of service
❌ Scrape copyrighted content for commercial use

## Support

If you encounter issues:

1. Check the console for detailed error messages
2. Verify API keys are valid (test in provider console)
3. Ensure Playwright is installed: `playwright install chromium`
4. Check network connectivity
5. Try with a different URL or AI provider

## Example: Full Workflow

```python
# 1. Add API key to .env
ANTHROPIC_API_KEY=sk-ant-api03-...

# 2. Restart app
streamlit run app.py

# 3. In UI:
#    - Go to "Search Discovery" tab
#    - Select "📄 Direct URL Scraping"
#    - Series: "IMSA WeatherTech"
#    - Season: 2026
#    - URL: https://www.imsa.com/weathertech/schedule/
#    - AI Provider: "Anthropic Claude"
#    - Click "🤖 Extract Data"

# 4. Review extracted data
# 5. Export or save to database
```

## Future Enhancements

Planned features:
- [ ] Multi-page scraping for paginated schedules
- [ ] Automatic retry with different AI provider
- [ ] Session detail pages scraping
- [ ] Result/standing extraction
- [ ] Configurable prompts per series
- [ ] Local LLM support (Ollama)
