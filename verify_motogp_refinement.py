import asyncio
from connectors.motogp import MotoGPConnector
from connectors.moto2 import Moto2Connector
from connectors.moto3 import Moto3Connector

async def verify():
    connectors = [MotoGPConnector(), Moto2Connector(), Moto3Connector()]
    season = 2026
    
    for conn in connectors:
        print(f"\nVerifying {conn.name}...")
        try:
            # We need a series_id, for MotoGP it's 'motogp', Moto2 'moto2', etc.
            sid = conn.id.split('_')[0]
            payload = conn.fetch_season(sid, season)
            events = conn.extract(payload)
            if events:
                first_event = events[0]
                print(f"Event: {first_event.name}")
                for s in first_event.sessions[:3]: # check first 3 sessions
                    print(f"  Session: {s.name}")
                    print(f"    Start: {s.start}")
                    print(f"    End: {s.end}")
            else:
                print("No events found")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
