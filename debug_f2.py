import sys
import os
import json
import logging

# Add project root to path
sys.path.append(os.getcwd())

from connectors.f2 import F2Connector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_f2():
    connector = F2Connector()
    print("Fetching F2 data...")
    try:
        payload = connector.fetch_season("f2", 2026) # or current year
        print(f"Payload Content Type: {payload.content_type}")
        print(f"Payload URL: {payload.url}")
        
        # We want to see the raw item structure that _parse_nextjs_event receives
        # We'll mimic the extraction logic briefly
        
        from bs4 import BeautifulSoup
        
        if payload.content_type == "text/html":
            soup = BeautifulSoup(payload.content, 'lxml')
            next_data = soup.find('script', id='__NEXT_DATA__')
            if next_data:
                data = json.loads(next_data.string)
                page_data = data.get('props', {}).get('pageProps', {}).get('pageData', {})
                races = page_data.get('Races', [])
                
                if races:
                    print(f"\n--- Found {len(races)} races ---")
                    for i, race in enumerate(races):
                        name = race.get('CircuitShortName', race.get('CountryName', "Unknown"))
                        r_start = race.get('RaceStartDate')
                        r_end = race.get('RaceEndDate')
                        sessions = race.get('Sessions', [])
                        
                        print(f"\nRound {i+1}: {name}")
                        print(f"  Dates: {r_start} to {r_end}")
                        print(f"  Sessions: {len(sessions)}")
                        for s in sessions:
                            s_name = s.get('SessionName')
                            s_start = s.get('SessionStartTime')
                            s_end = s.get('SessionEndTime')
                            print(f"    - {s_name}: {s_start} -> {s_end}")
                else:
                    print("No 'Races' found in pageData.")
            else:
                print("No __NEXT_DATA__ found.")
        else:
            print("Payload is not HTML (unexpected for current simple implementation).")
            print(payload.content[:500])

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_f2()
