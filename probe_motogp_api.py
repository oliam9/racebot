import httpx
import json

API_BASE = "https://api.pulselive.motogp.com/motogp/v1"
SEASON_ID = "e88b4e43-2209-47aa-8e83-0e0b1cedde6e"

def probe_endpoints():
    endpoints = [
        "schedule",
        "calendar/events",
        "events/calendar",
        f"results/events/{SEASON_ID}/sessions",
        "results/sessions/full",
    ]
    
    for ep in endpoints:
        url = f"{API_BASE}/{ep}"
        try:
            resp = httpx.get(url, timeout=5.0)
            print(f"Endpoint {ep}: {resp.status_code}")
            if resp.status_code == 200:
                print(f"Sample data from {ep}:")
                print(json.dumps(resp.json(), indent=2)[:500])
        except Exception as e:
            print(f"Endpoint {ep} failed: {e}")

if __name__ == "__main__":
    probe_endpoints()
