"""Test OpenF1 API"""
import httpx
import json

print("Testing OpenF1 API...")
print("="*60)

# Check available endpoints
base = "https://api.openf1.org/v1"

# Try to get sessions
url = f"{base}/sessions?year=2024"
print(f"\nTrying: {url}")
response = httpx.get(url, timeout=10)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = json.loads(response.text)
    print(f"✓ Found {len(data)} sessions for 2024")
    if data:
        print(f"\nFirst session sample:")
        print(json.dumps(data[0], indent=2)[:500])

# Try 2025
url = f"{base}/sessions?year=2025"
print(f"\n\nTrying: {url}")
response = httpx.get(url, timeout=10)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = json.loads(response.text)
    print(f"✓ Found {len(data)} sessions for 2025")
    
# Try 2026
url = f"{base}/sessions?year=2026"
print(f"\n\nTrying: {url}")
response = httpx.get(url, timeout=10)
print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = json.loads(response.text)
    print(f"✓ Found {len(data)} sessions for 2026")
    if data:
        print(f"\nFirst 2026 session:")
        print(json.dumps(data[0], indent=2))
else:
    print("⚠️ No 2026 data available yet")
