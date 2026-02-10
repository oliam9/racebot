"""
Test Gemini extraction on the properly loaded MotoGP HTML.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Read the good HTML from debug
with open(".cache/motogp_calendar_debug.html", "r", encoding="utf-8") as f:
    html = f.read()

print(f"Loaded HTML: {len(html):,} bytes")
print()

# Test both models
for model_name in ["gemini-2.5-flash", "gemini-2.5-pro"]:
    print(f"\n{'='*60}")
    print(f"Testing: {model_name}")
    print(f"{'='*60}\n")
    
    from search.ai_scraper import AIScraper
    
    try:
        scraper = AIScraper(
            ai_provider="google gemini",
            ai_model=model_name,
        )
        
        print(f"Extracting with {model_name}...")
        series_data = scraper._extract_with_ai(
            html_content=html,
            series_name="MotoGP World Championship",
            season_year=2026,
            source_url="https://www.motogp.com/en/calendar"
        )
        
        print(f"[OK] Extraction successful!")
        print(f"Series: {series_data.get('name')}")
        print(f"Season: {series_data.get('season')}")
        print(f"Events found: {len(series_data.get('events', []))}")
        
        events = series_data.get('events', [])
        if events:
            print(f"\nFirst 3 events:")
            for i, event in enumerate(events[:3], 1):
                print(f"  {i}. {event.get('name')} - {event.get('venue', {}).get('city')}")
        
    except Exception as e:
        print(f"[FAILED] {e}")
        import traceback
        traceback.print_exc()
