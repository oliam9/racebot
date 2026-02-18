"""
Registry of site-specific extraction hints for the Dynamic AI Connector.

This module maps domains (e.g. 'fiawec.com') to extraction strategies and hints
derived from our dedicated connectors. This allows the generic AI scraper to
be "smart" by using known API endpoints, CSS selectors, and JSON keys.
"""

from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

class SiteHint:
    """Hints for a specific site/domain."""
    def __init__(
        self,
        domain: str,
        strategy: str = "auto",  # api, nextdata, playwright, auto
        api_url: Optional[str] = None,
        calendar_path: Optional[str] = None,
        event_selectors: Optional[List[str]] = None,
        session_selectors: Optional[List[str]] = None,
        date_format: Optional[str] = None,
        json_keys: Optional[Dict[str, List[str]]] = None,
        network_patterns: Optional[List[str]] = None,
        ai_context: Optional[str] = None,
        timezone: Optional[str] = None,
        verify_ssl: bool = True,
    ):
        self.domain = domain
        self.strategy = strategy
        self.api_url = api_url
        self.calendar_path = calendar_path
        self.event_selectors = event_selectors or []
        self.session_selectors = session_selectors or []
        self.date_format = date_format
        self.json_keys = json_keys or {}
        self.network_patterns = network_patterns or []
        self.ai_context = ai_context
        self.timezone = timezone
        self.verify_ssl = verify_ssl


# ── Registry ──────────────────────────────────────────────────────────────────

_HINTS: Dict[str, SiteHint] = {}

def _register(hint: SiteHint):
    _HINTS[hint.domain] = hint

# ── 1. API-based Sites ────────────────────────────────────────────────────────

# Formula E (PulseLive)
_register(SiteHint(
    domain="fiaformulae.com",
    strategy="api",
    api_url="https://api.formula-e.pulselive.com/formula-e/v1/races",
    json_keys={
        "events": ["races", "events"],
        "name": ["city", "raceName", "name"],
        "start": ["date", "raceDate"],
        "sessions": ["sessions", "timetable"],
    },
    ai_context="Formula E uses PulseLive API. Sessions are often in 'sessions' or 'timetable' array.",
))

# NASCAR (CDN) - covers Cup, Xfinity, Truck
_register(SiteHint(
    domain="nascar.com",
    strategy="api",
    # Dynamic URL construction handled in connector, but we can hint the pattern
    network_patterns=["race_list_basic.json", "schedule-feed.json"],
    ai_context="NASCAR data is typically in JSON feeds. Look for run_type: 1=Practice, 2=Quali, 3=Race.",
    timezone="America/New_York", # Default fallback
))

# F1/F2/F3 (Next.js)
for domain in ["formula1.com", "fiaformula2.com", "fiaformula3.com", "f1academy.com"]:
    _register(SiteHint(
        domain=domain,
        strategy="nextdata",
        json_keys={
            "events": ["Races", "Events", "races"],
            "name": ["RaceName", "CircuitShortName", "Name"],
            "start": ["RaceStartDate", "Date", "StartDate"],
            "sessions": ["Sessions", "Timetable"],
        },
        ai_context="Modern Next.js site. Check __NEXT_DATA__ script tag for full props.",
    ))

# IndyCar (initially generic, but has JSON API logic in connector)
_register(SiteHint(
    domain="indycar.com",
    strategy="auto", # Mix of HTML and API
    network_patterns=["schedules", "race-control"],
    event_selectors=[".schedule-list-item", ".race-card"],
    ai_context="IndyCar schedule often in list items. Look for 'Race Control' links.",
    timezone="America/New_York",
))

# ── 2. Playwright / DOM Sites ─────────────────────────────────────────────────

# FIA WEC
_register(SiteHint(
    domain="fiawec.com",
    strategy="playwright",
    calendar_path="/en/season/calendar",
    event_selectors=[".calendar-list .item", ".race-card"],
    date_format="%d %B %Y", # 28 February 2026
    ai_context="FIA WEC: Events are in cards. Dates often span multiple days.",
    timezone="Europe/Paris", # Fallback
))

# FIA WRC
_register(SiteHint(
    domain="wrc.com",
    strategy="playwright",
    event_selectors=[".calendar-card", ".rally-card"],
    ai_context="WRC is an SPA. Events might be in grid cards. Dates are usually ranges.",
))

# IMSA
_register(SiteHint(
    domain="imsa.com",
    strategy="playwright",
    event_selectors=[".event-item", ".schedule-card"],
    ai_context="IMSA: Protected by Cloudflare. Look for 'WeatherTech Championship' events.",
    timezone="America/New_York",
))

# Supercars (Australia)
_register(SiteHint(
    domain="supercars.com",
    strategy="playwright",
    event_selectors=["a[href*='/events/']", ".event-card"],
    ai_context="Supercars: Australian text formats. Look for 'Race' vs 'SuperSprint'.",
    timezone="Australia/Sydney",
))

# BTCC
_register(SiteHint(
    domain="btcc.net",
    strategy="playwright",
    event_selectors=[".race-meeting", ".calendar-row"],
    ai_context="BTCC: UK based. 3 races per weekend. Look for 'Rounds'.",
    timezone="Europe/London",
))

# Super Formula (Japan)
_register(SiteHint(
    domain="superformula.net",
    strategy="playwright",
    verify_ssl=False, # Known issue
    ai_context="Super Formula: Japanese site. Dates might use YYYY.MM.DD format.",
    timezone="Asia/Tokyo",
))

# SRO (GT World Challenge) - Shared platform
for domain in [
    "gt-world-challenge-europe.com",
    "gt-world-challenge-america.com",
    "gt-world-challenge-asia.com",
    "intercontinentalgtchallenge.com"
]:
    _register(SiteHint(
        domain=domain,
        strategy="playwright",
        event_selectors=[".calendar-item", ".event-card"],
        ai_context="SRO Site: Events in calendar grid. Click event for timetable/sessions.",
    ))

# ── Helper ────────────────────────────────────────────────────────────────────

def get_hints_for_url(url: str) -> Optional[SiteHint]:
    """Find hints for a given URL by matching the domain."""
    if not url:
        return None
    
    try:
        parsed = urlparse(url)
        hostname = parsed.netloc.lower()
        
        # 1. Exact match
        if hostname in _HINTS:
            return _HINTS[hostname]
            
        # 2. Subdomain check (e.g. www.fiawec.com -> fiawec.com)
        # Sort hints by length (desc) to match specific subdomains first if any
        sorted_domains = sorted(_HINTS.keys(), key=len, reverse=True)
        for domain in sorted_domains:
            if hostname == domain or hostname.endswith("." + domain):
                return _HINTS[domain]
                
        return None
        
    except Exception:
        return None
