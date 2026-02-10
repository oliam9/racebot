"""
Summary of F1 and MotoGP Connectors for 2026 Season
"""

from connectors.f1 import F1Connector
from connectors.motogp import MotoGPConnector

def main():
    print("\n" + "=" * 70)
    print("🏁 RACEBOT - 2026 SEASON CONNECTORS SUMMARY")
    print("=" * 70)
    
    # F1 Summary
    print("\n📊 FORMULA 1 (OpenF1 API)")
    print("-" * 70)
    f1 = F1Connector()
    f1_raw = f1.fetch_season("f1", 2026)
    f1_events = f1.extract(f1_raw)
    
    print(f"  • Connector: {f1.name}")
    print(f"  • API Source: OpenF1 (https://openf1.org)")
    print(f"  • Total Races: {len(f1_events)}")
    print(f"  • Data Includes:")
    print(f"    - Race week, dates, location, circuit name")
    print(f"    - Sessions with precise timings (Practice, Qualifying, Sprint, Race)")
    print(f"    - Proper timezone support")
    
    # Show season span
    if f1_events:
        first = f1_events[0]
        last = f1_events[-1]
        print(f"  • Season: {first.start_date} to {last.end_date}")
        print(f"    - Opening: {first.name} ({first.venue.city})")
        print(f"    - Finale: {last.name} ({last.venue.city})")
    
    # MotoGP Summary
    print("\n📊 MOTOGP (PulseLive API)")
    print("-" * 70)
    motogp = MotoGPConnector()
    motogp_raw = motogp.fetch_season("motogp", 2026)
    motogp_events = motogp.extract(motogp_raw)
    
    print(f"  • Connector: {motogp.name}")
    print(f"  • API Source: MotoGP Official API")
    print(f"  • Total Races: {len(motogp_events)}")
    print(f"  • Data Includes:")
    print(f"    - Race week, dates, location, circuit name")
    print(f"    - Full session schedule (FP1-FP2, Qualifying, Warm Up, Sprint, Race)")
    print(f"    - Proper timezone support")
    
    # Show season span
    if motogp_events:
        first = motogp_events[0]
        last = motogp_events[-1]
        print(f"  • Season: {first.start_date} to {last.end_date}")
        print(f"    - Opening: {first.name} ({first.venue.city})")
        print(f"    - Finale: {last.name} ({last.venue.city})")
    
    # Data Format Summary
    print("\n📋 DATA FORMAT (All Connectors)")
    print("-" * 70)
    print("  Each event provides:")
    print("    ✓ Race Week: Sequential numbering (1, 2, 3...)")
    print("    ✓ Date: Start and end dates")
    print("    ✓ Location: City, region, country")
    print("    ✓ Circuit Name: Official track name")
    print("    ✓ Timezone: IANA timezone identifier")
    print("    ✓ Sessions: Name, type, start time, status")
    
    print("\n" + "=" * 70)
    print(f"✅ TOTAL: {len(f1_events) + len(motogp_events)} RACES AVAILABLE FOR 2026")
    print(f"   • Formula 1: {len(f1_events)} races")
    print(f"   • MotoGP: {len(motogp_events)} races")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
