"""
Analyze HTML from new connector websites to find embedded JSON data.
"""
import re
import json
from connectors import get_registry


def analyze_html_structure(series_id, connector_id):
    """Analyze HTML to find calendar data patterns."""
    registry = get_registry()
    connector = registry.get(connector_id)
    
    print(f"\n{'='*70}")
    print(f"Analyzing: {series_id}")
    print('='*70)
    
    try:
        raw = connector.fetch_season(series_id, 2025)
        html = raw.content
        
        # Look for various JSON patterns
        patterns = [
            (r'window\.__NUXT__\s*=\s*(\{.*?\});', 'NUXT'),
            (r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', 'INITIAL_STATE'),
            (r'window\.__DATA__\s*=\s*(\{.*?\});', 'DATA'),
            (r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', 'LD_JSON'),
            (r'var\s+calendar\s*=\s*(\[.*?\]);', 'calendar var'),
            (r'var\s+events\s*=\s*(\[.*?\]);', 'events var'),
            (r'"events"\s*:\s*(\[.*?\])', 'events property'),
            (r'"calendar"\s*:\s*(\[.*?\])', 'calendar property'),
        ]
        
        found_data = False
        
        for pattern, name in patterns:
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            if matches:
                print(f"  ✓ Found {name} pattern: {len(matches)} match(es)")
                
                # Try to parse first match
                try:
                    # Limit size for display
                    sample = matches[0][:500] if len(matches[0]) > 500 else matches[0]
                    print(f"    Sample: {sample}...")
                    
                    # Try to parse as JSON
                    data = json.loads(matches[0])
                    print(f"    Valid JSON! Keys: {list(data.keys()) if isinstance(data, dict) else 'Array'}")
                    found_data = True
                except:
                    print(f"    (Not valid JSON or too complex)")
        
        if not found_data:
            print(f"  No embedded JSON found in common patterns")
            print(f"  HTML size: {len(html)} bytes")
            
            # Check for common frameworks
            if 'nuxt' in html.lower():
                print(f"  Framework detected: Nuxt.js")
            if 'react' in html.lower():
                print(f"  Framework detected: React")
            if 'vue' in html.lower():
                print(f"  Framework detected: Vue")
            if 'angular' in html.lower():
                print(f"  Framework detected: Angular")
                
    except Exception as e:
        print(f"  ✗ Error: {e}")


if __name__ == "__main__":
    configs = [
        ("dtm", "dtm_official"),
        ("f2", "f2_official"),
        ("f3", "f3_official"),
        ("worldrx", "worldrx_official"),
        ("worldsbk", "worldsbk_official"),
    ]
    
    for series_id, connector_id in configs:
        analyze_html_structure(series_id, connector_id)
