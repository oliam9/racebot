"""
Test F1 connector for 2026 season.
"""

from connectors.f1 import F1Connector
from datetime import datetime

def test_f1_2026():
    print("=" * 60)
    print("Testing F1 Connector - 2026 Season")
    print("=" * 60)
    
    connector = F1Connector()
    print(f"\n✓ Connector: {connector.name}")
    print(f"  ID: {connector.id}")
    print(f"  Supported: {[s.name for s in connector.supported_series()]}")
    
    try:
        # Fetch 2026 season
        print("\n📡 Fetching F1 2026 season...")
        raw = connector.fetch_season("f1", 2026)
        print(f"✓ Fetched: {len(raw.content)} bytes")
        print(f"  URL: {raw.url}")
        print(f"  Retrieved: {raw.retrieved_at}")
        
        # Extract events
        print("\n🏁 Extracting events...")
        events = connector.extract(raw)
        print(f"✓ Found {len(events)} races")
        
        if not events:
            print("⚠️  No races found for 2026 season")
            print("   (Ergast API may not have 2026 data yet)")
            return
        
        # Show first 3 races
        print("\n" + "=" * 60)
        print("First 3 Races:")
        print("=" * 60)
        
        for idx, event in enumerate(events[:3], 1):
            print(f"\n🏎️  Race {idx}: {event.name}")
            print(f"   Dates: {event.start_date} to {event.end_date}")
            print(f"   Circuit: {event.venue.circuit}")
            print(f"   Location: {event.venue.city}, {event.venue.country}")
            print(f"   Timezone: {event.venue.timezone}")
            print(f"   Sessions: {len(event.sessions)}")
            
            if event.sessions:
                print("\n   Session Schedule:")
                for session in event.sessions:
                    start_time = session.start if session.start else "TBD"
                    if len(start_time) > 25:
                        # Format datetime for display
                        try:
                            dt = datetime.fromisoformat(start_time)
                            start_time = dt.strftime("%a %b %d, %I:%M %p")
                        except:
                            pass
                    print(f"      • {session.name}: {start_time}")
        
        print("\n" + "=" * 60)
        print(f"✓ F1 Connector Test Complete - {len(events)} races")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_f1_2026()
