"""Debug F1 API response."""
import httpx

# Try 2024 first to see if API works
for year in [2024, 2025, 2026]:
    print(f"\n{'='*60}")
    print(f"Testing Year: {year}")
    print('='*60)
    
    url = f"http://ergast.com/api/f1/{year}.json"
    response = httpx.get(url, timeout=10, follow_redirects=True)
    
    print(f"Status: {response.status_code}")
    print(f"Final URL: {response.url}")
    print(f"Content-Type: {response.headers.get('content-type')}")
    
    # Try to parse as JSON
    import json
    try:
        data = json.loads(response.text)
        print("✓ Valid JSON response")
        
        # Check for races
        race_table = data.get("MRData", {}).get("RaceTable", {})
        races = race_table.get("Races", [])
        print(f"✓ Found {len(races)} races")
        if races and len(races) > 0:
            print(f"  First race: {races[0].get('raceName', 'N/A')}")
            print(f"  Circuit: {races[0].get('Circuit', {}).get('circuitName', 'N/A')}")
    except Exception as e:
        print(f"❌ Not JSON (likely HTML redirect): {str(e)[:100]}")
