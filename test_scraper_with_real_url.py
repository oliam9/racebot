"""
Test the AI scraper with a real motorsports URL.
Tests both HTTP and Playwright modes.
"""
import os
from dotenv import load_dotenv
from search.ai_scraper import AIScraper

# Load environment variables from .env
load_dotenv()

# Sample URLs to test
TEST_URLS = {
    "IMSA WeatherTech": {
        "url": "https://www.imsa.com/weathertech/schedule/",
        "series": "IMSA WeatherTech SportsCar Championship",
        "season": 2026,
        "note": "Static HTML, works without Playwright"
    },
    "WEC": {
        "url": "https://www.fia.com/wec/calendar",
        "series": "FIA World Endurance Championship",
        "season": 2026,
        "note": "Static HTML, works without Playwright"
    },
    "DTM": {
        "url": "https://www.dtm.com/en/events",
        "series": "DTM - Deutsche Tourenwagen Masters",
        "season": 2025,
        "note": "May need Playwright for JavaScript"
    },
    "MotoGP": {
        "url": "https://www.motogp.com/en/calendar",
        "series": "MotoGP World Championship",
        "season": 2026,
        "note": "JavaScript-heavy, may need Playwright"
    }
}


def test_with_url(name: str, config: dict, ai_model: str = "gemini-2.5-flash"):
    """Test scraping with a specific URL."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"URL: {config['url']}")
    print(f"AI Model: {ai_model}")
    print(f"Note: {config['note']}")
    print(f"{'='*60}\n")
    
    # Check environment
    playwright_enabled = os.environ.get("PLAYWRIGHT_ENABLED", "true").lower() == "true"
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    
    print(f"Environment:")
    print(f"  Playwright: {'[YES] Enabled' if playwright_enabled else '[NO] Disabled (HTTP only)'}")
    print(f"  Gemini Key: {'[YES] Found' if gemini_key else '[NO] Missing'}")
    print()
    
    if not gemini_key:
        print("[ERROR] GEMINI_API_KEY not found in .env!")
        return False
    
    try:
        # Initialize scraper
        print(f"Initializing AI scraper with {ai_model}...")
        scraper = AIScraper(
            ai_provider="google gemini",
            ai_model=ai_model,
            requests_per_minute=3,
            cache_hours=24
        )
        print("[OK] Scraper initialized\n")
        
        # Scrape the page
        print(f"Scraping {config['url']}...")
        result = scraper.scrape_schedule_page(
            url=config['url'],
            series_name=config['series'],
            season_year=config['season']
        )
        
        # Display results
        print(f"\n{'='*60}")
        print("RESULTS:")
        print(f"{'='*60}")
        print(f"Success: {result.success}")
        print(f"Cached: {result.cached}")
        print(f"Fetch time: {result.fetch_time_ms:.0f}ms")
        print(f"Extraction time: {result.extraction_time_ms:.0f}ms")
        print(f"Content size: {result.content_length:,} bytes")
        
        if result.error_message:
            print(f"\n[ERROR] {result.error_message}")
        
        if result.success and result.series_data:
            data = result.series_data
            print(f"\n[SUCCESS] EXTRACTION COMPLETE!")
            print(f"\nSeries: {data.get('name', 'N/A')}")
            print(f"Season: {data.get('season', 'N/A')}")
            
            events = data.get('events', [])
            print(f"Events found: {len(events)}")
            
            if events:
                print(f"\nFirst 3 events:")
                for i, event in enumerate(events[:3], 1):
                    print(f"\n  {i}. {event.get('name', 'N/A')}")
                    print(f"     Date: {event.get('date', 'N/A')}")
                    print(f"     Venue: {event.get('venue', {}).get('name', 'N/A')}")
                    print(f"     Location: {event.get('venue', {}).get('city', 'N/A')}, {event.get('venue', {}).get('country', 'N/A')}")
            
            return True
        else:
            print(f"\n[FAILED] Extraction failed or returned no data")
            return False
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run tests."""
    print("="*60)
    print("AI SCRAPER - REAL URL TEST")
    print("="*60)
    
    # You can change the model here: "gemini-2.5-flash", "gemini-2.5-pro", or "gemini-2.0-flash-exp"
    ai_model = "gemini-2.0-flash-exp"  # Using experimental model for latest features
    
    # Test with DTM (may need Playwright for JavaScript)
    success = test_with_url("DTM", TEST_URLS["DTM"], ai_model=ai_model)
    
    if not success:
        print("\n[WARNING] Test  failed. Try these fixes:")
        print("1. Check your .env file has GEMINI_API_KEY set")
        print("2. If you see 403 errors, try setting PLAYWRIGHT_ENABLED=true")
        print("3. Install Playwright: python -m playwright install chromium")
        print("4. Check the URL is still valid")
    
    print("\n" + "="*60)
    print("Want to test other URLs?")
    print("- IMSA: Change 'DTM' to 'IMSA WeatherTech' in main()")
    print("- WEC: Change 'DTM' to 'WEC' in main()")
    print("- MotoGP: Change 'DTM' to 'MotoGP' in main()")
    print("="*60)


if __name__ == "__main__":
    main()
