import httpx
import json

API_BASE = "https://api.pulselive.motogp.com/motogp/v1"

def get_latest_season_id():
    url = f"{API_BASE}/results/seasons"
    resp = httpx.get(url)
    resp.raise_for_status()
    seasons = resp.json()
    # Sort by year desc
    seasons.sort(key=lambda x: x['year'], reverse=True)
    if seasons:
        latest = seasons[0]
        print(f"Latest season: {latest['year']} ({latest['id']})")
        return latest['id']
    return None

def get_categories(season_uuid):
    url = f"{API_BASE}/results/categories"
    params = {"seasonUuid": season_uuid}
    resp = httpx.get(url, params=params)
    resp.raise_for_status()
    categories = resp.json()
    print(json.dumps(categories, indent=2))

if __name__ == "__main__":
    sid = get_latest_season_id()
    if sid:
        get_categories(sid)
