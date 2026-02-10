"""
Quick test script to verify AI scraper setup.
Run this to check if everything is configured correctly.
"""

import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

print("🔍 AI Scraper Configuration Check\n")
print("=" * 60)

# Check environment variables
print("\n1. API Keys:")
print("-" * 60)

# anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")  # Commented out for now
gemini_key = os.environ.get("GEMINI_API_KEY", "")
playwright_enabled = os.environ.get("PLAYWRIGHT_ENABLED", "true")

# if anthropic_key:
#     print(f"✅ Anthropic API Key: Found ({anthropic_key[:10]}...)")
# else:
#     print("❌ Anthropic API Key: Not found")

if gemini_key:
    print(f"✅ Gemini API Key: Found ({gemini_key[:10]}...)")
else:
    print("❌ Gemini API Key: Not found")

print(f"{'✅' if playwright_enabled.lower() == 'true' else '⚠️'} Playwright: {playwright_enabled}")

# Check installed packages
print("\n2. Required Packages:")
print("-" * 60)

packages = {
    # "anthropic": "Anthropic Claude API",  # Commented out for now
    "google.generativeai": "Google Gemini API",
    "playwright": "Browser automation",
    "httpx": "HTTP client",
    "selectolax": "HTML parsing",
}

for package, description in packages.items():
    try:
        __import__(package.replace("google.generativeai", "google").split(".")[0])
        print(f"✅ {package}: Installed ({description})")
    except ImportError:
        print(f"❌ {package}: NOT INSTALLED ({description})")

# Test AI Scraper initialization
print("\n3. AI Scraper Initialization:")
print("-" * 60)

try:
    from search.ai_scraper import AIScraper
    
    # if anthropic_key:  # Commented out for now
    #     try:
    #         scraper = AIScraper(ai_provider="anthropic claude")
    #         print("✅ Anthropic scraper: Initialized successfully")
    #     except Exception as e:
    #         print(f"❌ Anthropic scraper: Failed - {str(e)}")
    
    if gemini_key:
        try:
            scraper = AIScraper(ai_provider="google gemini")
            print("✅ Gemini scraper: Initialized successfully")
        except Exception as e:
            print(f"❌ Gemini scraper: Failed - {str(e)}")
    else:
        print("⚠️ No Gemini API key found - skipping initialization test")
except Exception as e:
    print(f"❌ Failed to import AIScraper: {str(e)}")

# Test rate limiter
print("\n4. Safety Features:")
print("-" * 60)

try:
    from search.ai_scraper import RateLimiter, ResponseCache
    
    limiter = RateLimiter(requests_per_minute=3)
    print("✅ Rate Limiter: Working (3 req/min)")
    
    cache = ResponseCache()
    print(f"✅ Response Cache: Working (dir: {cache.cache_dir})")
except Exception as e:
    print(f"❌ Safety features: Failed - {str(e)}")

# Summary
print("\n" + "=" * 60)
print("SETUP STATUS:")
print("=" * 60)

if gemini_key:
    print("✅ Ready to use AI-powered scraping with Google Gemini!")
    print("\nNext steps:")
    print("1. Run: streamlit run app.py")
    print("2. Go to 'Search Discovery' tab")
    print("3. Select '📄 Direct URL Scraping' mode")
    print("4. Enter a schedule URL and extract!")
    print("\n💡 Tip: Gemini is FREE for up to 60 requests/minute")
else:
    print("⚠️ Setup incomplete!")
    print("\nTo get started:")
    print("1. Get API key from: https://makersuite.google.com/app/apikey")
    print("2. Add to .env file:")
    print("   GEMINI_API_KEY=your_key_here")
    print("3. Restart this test script")

print("\nFor detailed setup guide, see: AI_SCRAPING_GUIDE.md")
print("=" * 60)
