"""Test OpenF1 meetings endpoint"""
import httpx
import json

print("Testing OpenF1 Meetings API...")
print("="*60)

base = "https://api.openf1.org/v1"

# Get meetings for 2026
url = f"{base}/meetings?year=2026"
print(f"\nTrying: {url}")
response = httpx.get(url, timeout=10)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = json.loads(response.text)
    print(f"✓ Found {len(data)} meetings (race weekends) for 2026")
    
    if data:
        print(f"\n{'='*60}")
        print("First 3 meetings:")
        print('='*60)
        for i, meeting in enumerate(data[:3], 1):
            print(f"\n{i}. {meeting.get('meeting_name', 'N/A')}")
            print(f"   Official: {meeting.get('meeting_official_name', 'N/A')}")
            print(f"   Location: {meeting.get('location', 'N/A')}")
            print(f"   Country: {meeting.get('country_name', 'N/A')} ({meeting.get('country_code', 'N/A')})")
            print(f"   Circuit: {meeting.get('circuit_short_name', 'N/A')}")
            print(f"   Dates: {meeting.get('date_start', 'N/A')} to {meeting.get('date_end', 'N/A')}")
            print(f"   GMT Offset: {meeting.get('gmt_offset', 'N/A')}")
            print(f"   Meeting Key: {meeting.get('meeting_key', 'N/A')}")
        
        # Now get sessions for first meeting
        first_meeting_key = data[0].get('meeting_key')
        print(f"\n{'='*60}")
        print(f"Sessions for {data[0].get('meeting_name')}:")
        print('='*60)
        
        sessions_url = f"{base}/sessions?meeting_key={first_meeting_key}"
        sessions_resp = httpx.get(sessions_url, timeout=10)
        if sessions_resp.status_code == 200:
            sessions = json.loads(sessions_resp.text)
            print(f"✓ Found {len(sessions)} sessions")
            for session in sessions:
                print(f"  • {session.get('session_name', 'N/A')} ({session.get('session_type', 'N/A')})")
                print(f"    Start: {session.get('date_start', 'N/A')}")
