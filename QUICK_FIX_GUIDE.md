# Quick Fix Guide for Playwright & Gemini Issues

## ✅ FIXED: Gemini Model Error

**Issue**: `404 models/gemini-1.5-flash-latest is not found`

**Solution**: Updated to use the correct model: `gemini-2.5-flash`

**Test passed**: ✅ Gemini AI extraction is now working!

---

## 🔧 FIX: Playwright Browser Installation

### The Problem
When you try to scrape websites, you might see:
- `403 Forbidden` errors
- "Browser not initialized or disabled"
- "Playwright fetch failed"

### The Solution - Install Playwright Browsers

Run this command in your terminal:

```bash
python -m playwright install chromium
```

If that fails, try:

```bash
# Install with dependencies
playwright install chromium --with-deps

# Or use pip to reinstall playwright first
pip install --upgrade playwright
python -m playwright install chromium
```

### Alternative: Disable Playwright (Use Simple HTTP)

If Playwright installation fails or you want to avoid browser automation, you can disable it:

**In your `.env` file:**
```env
PLAYWRIGHT_ENABLED=false
```

This will make the scraper use simple HTTP requests instead. This works for:
- ✅ Static HTML pages
- ✅ Simple schedule pages
- ❌ JavaScript-heavy sites (MotoGP, some modern sites)

---

## 🧪 Test Your Setup

### Test 1: Check Gemini AI (SHOULD WORK NOW)
```bash
python test_gemini_extraction.py
```

Expected: ✅ Extraction successful!

### Test 2: Check Playwright Installation
```bash
python -c "from playwright.sync_api import sync_playwright; print('✅ Playwright ready')"
```

### Test 3: Full Setup Check
```bash
python test_ai_scraper_setup.py
```

---

## 🌐 Recommended: Start with Simple Sites

While Playwright is installing, test with sites that work via simple HTTP:

### Good starter URLs (work without Playwright):
```
https://www.imsa.com/weathertech/schedule/
https://www.fia.com/wec/calendar
```

### Might need Playwright:
```
https://www.motogp.com/en/calendar
https://www.dtm.com/en/schedule
```

---

## 📝 Status Summary

| Component | Status | Notes |
|-----------|--------|-------|
| ✅ Gemini AI | **WORKING** | Model fixed to `gemini-2.5-flash` |
| ✅ API Key | **WORKING** | Found in `.env` |
| ⚠️ Playwright | **NEEDS INSTALL** | Run: `python -m playwright install chromium` |
| ✅ HTTP Fallback | **READY** | Works if Playwright disabled |
| ✅ Rate Limiting | **ACTIVE** | 3 requests/minute |
| ✅ Caching | **ACTIVE** | 24-hour cache |

---

## 🚀 Quick Start (Right Now)

You can actually use the scraper RIGHT NOW without Playwright:

1. **Disable Playwright** in `.env`:
   ```env
   PLAYWRIGHT_ENABLED=false
   ```

2. **Run the app**:
   ```bash
   streamlit run app.py
   ```

3. **Try scraping** a simple site:
   - Go to "Search Discovery" tab
   - Select "📄 Direct URL Scraping"
   - Series: IMSA WeatherTech
   - Season: 2026
   - URL: `https://www.imsa.com/weathertech/schedule/`
   - Click "🤖 Extract Data"

4. **If it works**, great! If you get better results, install Playwright later.

---

## 💡 Troubleshooting

### Error: "403 Forbidden"
**Cause**: Website is blocking simple HTTP requests

**Solution**:
1. Install Playwright: `python -m playwright install chromium`
2. Enable in `.env`: `PLAYWRIGHT_ENABLED=true`

### Error: "Browser not initialized"
**Cause**: Playwright browsers not installed

**Solution**: Run `python -m playwright install chromium`

### Error: "Gemini model not found"
**Status**: ✅ FIXED! (Updated to `gemini-2.5-flash`)

---

## 📊 What Changed

### Files Updated:
1. `search/ai_scraper.py`:
   - ✅ Fixed Gemini model: `gemini-1.5-flash-latest` → `gemini-2.5-flash`
   - ✅ Better Playwright error handling
   - ✅ Check `PLAYWRIGHT_ENABLED` environment variable
   - ✅ Graceful fallback to HTTP

2. `ui/search_fallback.py`:
   - ✅ Simplified to Gemini-only
   - ✅ Updated help text

3. `.env.example`:
   - ✅ Commented out Anthropic
   - ✅ Focused on Gemini

---

## 🎯 Next Actions

Choose one:

### Option A: Install Playwright (Recommended)
```bash
python -m playwright install chromium
```
Then test in Streamlit!

### Option B: Use Without Playwright (Quick Start)
1. Set `PLAYWRIGHT_ENABLED=false` in `.env`
2. Run `streamlit run app.py`
3. Test with IMSA URL
4. Install Playwright later if needed

---

Need help? The scraper is working with Gemini - Playwright is optional for many sites!
