import httpx
import json

API_BASE = "https://api.pulselive.motogp.com/motogp/v1"
SEASON_ID = "e88b4e43-2209-47aa-8e83-0e0b1cedde6e"
CAT_ID = "e8c110ad-64aa-4e8e-8a86-f2f152f6a942"

def get_events():
    url = f"{API_BASE}/results/events"
    params = {"seasonUuid": SEASON_ID, "isTest": "false"}
    resp = httpx.get(url, params=params)
    resp.raise_for_status()
    return resp.json()

def get_sessions(event_id):
    url = f"{API_BASE}/results/sessions"
    params = {"eventUuid": event_id, "categoryUuid": CAT_ID}
    resp = httpx.get(url, params=params)
    resp.raise_for_status()
    sessions = resp.json()
    if sessions:
        print("Keys in a session object:")
        print(list(sessions[0].keys()))
        # Check for duration or end related keys specifically
        for key in sessions[0].keys():
            if any(term in key.lower() for term in ['end', 'duration', 'min', 'time', 'len']):
                print(f"Potential time field: {key} = {sessions[0][key]}")
        
    return sessions

if __name__ == "__main__":
    events = get_events()
    if events:
        first_event = next((e for e in events if e.get('id')), None)
        if first_event:
            get_sessions(first_event.get('id'))
