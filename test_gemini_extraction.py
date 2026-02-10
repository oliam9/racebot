"""
Quick test to verify Gemini AI extraction works with the new model.
"""

import os
from dotenv import load_dotenv

load_dotenv()

print("🧪 Testing Gemini AI Extraction\n")
print("=" * 60)

# Test HTML content (simple schedule example)
test_html = """
<html>
<body>
<h1>2026 IMSA WeatherTech Schedule</h1>
<div class="event">
    <h2>Rolex 24 at Daytona</h2>
    <p>Date: January 25-26, 2026</p>
    <p>Location: Daytona International Speedway, Daytona Beach, Florida</p>
</div>
<div class="event">
    <h2>Mobil 1 Twelve Hours of Sebring</h2>
    <p>Date: March 20, 2026</p>
    <p>Location: Sebring International Raceway, Sebring, Florida</p>
</div>
</body>
</html>
"""

try:
    print("\n1. Initializing Gemini AI...")
    from search.ai_scraper import AIScraper
    
    scraper = AIScraper(ai_provider="google gemini")
    print("✅ Gemini AI initialized successfully")
    print(f"   Model: gemini-2.5-flash")
    
    print("\n2. Testing AI extraction...")
    print("-" * 60)
    
    # Extract data
    result = scraper._extract_with_ai(
        html_content=test_html,
        series_name="IMSA WeatherTech",
        season_year=2026,
        source_url="https://test.example.com"
    )
    
    print("✅ Extraction successful!")
    print(f"\n3. Results:")
    print("-" * 60)
    
    if isinstance(result, dict):
        print(f"   Series: {result.get('name', 'N/A')}")
        print(f"   Season: {result.get('season', 'N/A')}")
        print(f"   Events found: {len(result.get('events', []))}")
        
        if result.get('events'):
            print(f"\n   First event:")
            event = result['events'][0]
            print(f"   - Name: {event.get('name', 'N/A')}")
            print(f"   - Date: {event.get('start_date', 'N/A')}")
            print(f"   - Venue: {event.get('venue', {}).get('circuit', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("✅ TEST PASSED - Gemini AI extraction working!")
    print("=" * 60)
    
except Exception as e:
    print("\n" + "=" * 60)
    print("❌ TEST FAILED")
    print("=" * 60)
    print(f"Error: {str(e)}")
    
    import traceback
    print("\nFull error:")
    print(traceback.format_exc())
