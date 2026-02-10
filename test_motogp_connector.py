"""Test MotoGP connector for 2026 season."""
from connectors.motogp import MotoGPConnector

def test_motogp_2026():
    print("=" * 60)
    print("Testing MotoGP Connector - 2026 Season")
    print("=" * 60)
    
    connector = MotoGPConnector()
    print(f"\n✓ Connector: {connector.name}")
    print(f"  ID: {connector.id}")
    
    try:
        # Fetch 2026 season
        print("\n📡 Fetching MotoGP 2026 season...")
        raw = connector.fetch_season("motogp", 2026)
        print(f"✓ Fetched: {len(raw.content)} bytes")
        
        # Extract events
        print("\n🏁 Extracting events...")
        events = connector.extract(raw)
        print(f"✓ Found {len(events)} races")
        
        if not events:
            print("⚠️  No races found for 2026")
            return
        
        # Show first 3 races
        print("\n" + "=" * 60)
        print("First 3 Races:")
        print("=" * 60)
        
        for idx, event in enumerate(events[:3], 1):
            print(f"\n🏍️  Race {idx}: {event.name}")
            print(f"   Dates: {event.start_date} to {event.end_date}")
            print(f"   Circuit: {event.venue.circuit}")
            print(f"   Location: {event.venue.city}, {event.venue.country}")
            print(f"   Timezone: {event.venue.timezone}")
            print(f"   Sessions: {len(event.sessions)}")
            
            if event.sessions:
                print("\n   Session Schedule:")
                for session in event.sessions[:5]:  # First 5 sessions
                    print(f"      • {session.name}: {session.start if session.start else 'TBD'}")
        
        print("\n" + "=" * 60)
        print(f"✓ MotoGP Connector Test Complete - {len(events)} races")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_motogp_2026()
