"""
Dynamic AI Connector — smart scraping for any motorsport website.

Four-tier strategy:
  1. INLINE JSON    — __NEXT_DATA__, embedded JSON in HTML (F1/F2/F3 Next.js)
  2. NETWORK CAPTURE — intercept XHR/fetch API responses via Playwright
  3. AI EXTRACTION  — Gemini AI reads the HTML and extracts schedule data
  4. AI TWO-PHASE   — AI reads calendar, then drills into each event page

After tiers 1-2, if events are found without sessions, the connector
automatically visits event detail pages (via path/URL metadata) to fetch
session data (network capture or inline JSON on the detail page).

Handles multiple data formats: F1/F2/F3, Formula E, MotoGP, generic.
"""

import json
import logging
import re
import time
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

from connectors.base import Connector, RawSeriesPayload
from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SessionType, SessionStatus, SeriesCategory
from connectors.site_hints import get_hints_for_url, SiteHint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config / mappings
# ---------------------------------------------------------------------------

_SERIES_CONFIGS: Dict[str, Dict[str, Any]] = {
    "motogp": {"name": "MotoGP", "category": SeriesCategory.MOTORCYCLE},
    "moto2": {"name": "Moto2", "category": SeriesCategory.MOTORCYCLE},
    "moto3": {"name": "Moto3", "category": SeriesCategory.MOTORCYCLE},
    "f1": {"name": "Formula 1", "category": SeriesCategory.OPENWHEEL},
    "f2": {"name": "Formula 2", "category": SeriesCategory.OPENWHEEL},
    "f3": {"name": "Formula 3", "category": SeriesCategory.OPENWHEEL},
    "indycar": {"name": "IndyCar", "category": SeriesCategory.OPENWHEEL},
    "worldsbk": {"name": "World Superbike", "category": SeriesCategory.MOTORCYCLE},
    "worldrx": {"name": "World Rallycross", "category": SeriesCategory.RALLY},
    "dtm": {"name": "DTM", "category": SeriesCategory.GT},
    "nascar": {"name": "NASCAR", "category": SeriesCategory.TOURING},
    "wec": {"name": "FIA WEC", "category": SeriesCategory.ENDURANCE},
    "imsa": {"name": "IMSA WeatherTech", "category": SeriesCategory.ENDURANCE},
    "wrc": {"name": "WRC", "category": SeriesCategory.RALLY},
    "formula_e": {"name": "Formula E", "category": SeriesCategory.OPENWHEEL},
    "btcc": {"name": "BTCC", "category": SeriesCategory.TOURING},
    "gt_world_challenge": {"name": "GT World Challenge", "category": SeriesCategory.GT},
    "custom": {"name": "Custom Series", "category": SeriesCategory.OTHER},
}

_SESSION_TYPE_MAP = {
    "PRACTICE": SessionType.PRACTICE,
    "FREE PRACTICE": SessionType.PRACTICE,
    "QUALIFYING": SessionType.QUALIFYING,
    "RACE": SessionType.RACE,
    "SPRINT": SessionType.SPRINT,
    "WARMUP": SessionType.WARMUP,
    "TEST": SessionType.TEST,
    "OTHER": SessionType.OTHER,
    "RESULT": SessionType.RACE,
    "FP": SessionType.PRACTICE,
    "Q": SessionType.QUALIFYING,
    "RAC": SessionType.RACE,
    "SPR": SessionType.SPRINT,
    "WUP": SessionType.WARMUP,
}

_SESSION_STATUS_MAP = {
    "SCHEDULED": SessionStatus.SCHEDULED,
    "TBD": SessionStatus.TBD,
    "UPDATED": SessionStatus.UPDATED,
    "CANCELLED": SessionStatus.CANCELLED,
    "PRE-RACE": SessionStatus.SCHEDULED,
    "POST-RACE": SessionStatus.SCHEDULED,
    "NOT_STARTED": SessionStatus.SCHEDULED,
    "RACE_NOT_STARTED": SessionStatus.SCHEDULED,
}

# Network capture patterns — broad to catch most APIs
_CALENDAR_PATTERNS = [
    "calendar", "schedule", "races", "events", "season",
    "rounds", "meeting", "timetable", "programme",
    "championship", "series", "results",
]


class DynamicAIConnector(Connector):
    """Smart scraper: tries inline JSON → network capture → AI extraction."""

    def __init__(self):
        super().__init__()
        self._target_url: Optional[str] = None
        self._progress_callback = None
        self._upcoming_only: bool = False

    @property
    def id(self) -> str:
        return "dynamic_ai"

    @property
    def name(self) -> str:
        return "🤖 Dynamic AI Scraper"

    @property
    def needs_url(self) -> bool:
        return True

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id=sid,
                name=f"{cfg['name']} (AI)",
                category=cfg["category"],
                connector_id=self.id,
            )
            for sid, cfg in _SERIES_CONFIGS.items()
        ]

    def set_target_url(self, url: str):
        self._target_url = url

    def set_upcoming_only(self, upcoming: bool):
        self._upcoming_only = upcoming

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def _progress(self, msg: str):
        logger.info(msg)
        if self._progress_callback:
            try:
                self._progress_callback(msg)
            except Exception:
                pass

    # =====================================================================
    # MAIN ENTRY
    # =====================================================================



    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        """
        Four-tier smart scraping:
        1. Site Hints API (if available) -> Direct API call
        2. Inline JSON (Next.js, Nuxt, etc)
        3. Network Capture (XHR interception)
        4. AI Extraction (Gemini)
        """
        if not self._target_url:
            raise ValueError("Target URL not set. Call set_target_url() first.")

        url = self._target_url
        series_cfg = _SERIES_CONFIGS.get(series_id, _SERIES_CONFIGS["custom"])
        series_name = series_cfg["name"]

        # 0. Check Hints Registry
        hint: Optional[SiteHint] = get_hints_for_url(url)
        if hint:
            self._progress(f"💡 Found site hints for {hint.domain} ({hint.strategy})")

            # Strategy: Direct API (e.g. Formula E, NASCAR)
            if hint.strategy == "api" and hint.api_url:
                self._progress(f"⚡ Using known API endpoint: {hint.api_url}")
                try:
                    import httpx
                    # Some APIs need year replacement
                    api_url = hint.api_url.format(year=season)
                    # Simple GET
                    with httpx.Client(timeout=30.0, verify=hint.verify_ssl) as client:
                        resp = client.get(api_url)
                        resp.raise_for_status()
                        data = resp.json()
                        result = self._parse_generic_json(data, series_name, season, hint)
                        if result and result.get("events"):
                            result = self._enrich_events(result, url, series_name, season)
                            return self._pack(result, url, series_id, season, "hint_api")
                except Exception as e:
                    logger.warning(f"Hint API failed: {e}")

        # Fetch the page HTML — needed by multiple tiers
        self._progress("📄 Fetching page...")
        html = self._fetch_html(url)

        # ── Tier 1: Inline JSON ──────────────────────────────────────
        self._progress("🔍 Tier 1: Looking for embedded JSON data...")
        data = self._try_inline_json(html, series_name, season, hint)
        if data and data.get("events"):
            data = self._enrich_events(data, url, series_name, season)
            return self._pack(data, url, series_id, season, "inline_json")

        # ── Tier 2: Network capture ──────────────────────────────────
        self._progress("🔍 Tier 2: Intercepting network API requests...")
        data = self._try_network_capture(url, series_name, season, hint)
        if data and data.get("events"):
            data = self._enrich_events(data, url, series_name, season)
            return self._pack(data, url, series_id, season, "api_capture")

        # ── Tier 3: AI Single Page ───────────────────────────────────
        self._progress("🧠 Tier 3: analyzing page with Gemini AI...")
        data = self._try_ai_single(html, series_name, season, hint)
        if data and data.get("events"):
            data = self._enrich_events(data, url, series_name, season)
            return self._pack(data, url, series_id, season, "ai_single")

        # ── Tier 4: AI Two-Phase ─────────────────────────────────────
        self._progress("🧠 Tier 4: performing deep AI extraction...")
        data = self._try_ai_two_phase(html, url, series_name, season, hint)
        if data and data.get("events"):
            # No enrich needed, two-phase handles detailed sessions
            return self._pack(data, url, series_id, season, "ai_two_phase")

        # Only return empty payload if nothing found
        return self._pack(
            {"series_id": series_id, "name": series_name, "season": season, "events": []},
            url, series_id, season, "none",
        )

    def _enrich_events(self, data: Dict, base_url: str,
                       series_name: str, season: int) -> Dict:
        """Post-process: filter upcoming, fetch sessions, fix dates."""
        events = data.get("events", [])

        # Filter upcoming only
        if self._upcoming_only:
            today_str = date.today().isoformat()
            before = len(events)
            events = [
                e for e in events
                if (e.get("end_date", e.get("start_date", "")) >= today_str
                    or not e.get("has_results", False))
            ]
            dropped = before - len(events)
            if dropped:
                self._progress(f"📅 Filtered to {len(events)} upcoming (dropped {dropped} past)")

        # Fetch sessions for events that have none but have detail URLs
        needs_sessions = [e for e in events if not e.get("sessions") and e.get("detail_url")]
        if needs_sessions:
            self._progress(
                f"📋 {len(needs_sessions)} events have no sessions — "
                f"fetching detail pages..."
            )
            for i, evt in enumerate(needs_sessions, 1):
                detail_url = evt["detail_url"]
                evt_name = evt.get("name", f"Event {i}")
                self._progress(f"   [{i}/{len(needs_sessions)}] {evt_name}...")
                sessions = self._fetch_detail_sessions(detail_url)
                if sessions:
                    evt["sessions"] = sessions
                    self._progress(f"   ✅ {len(sessions)} sessions for {evt_name}")
                else:
                    self._progress(f"   📭 No sessions found for {evt_name}")
                if i < len(needs_sessions):
                    time.sleep(1.5)

        # Recalculate end_date from session dates for each event
        for evt in events:
            self._fix_event_dates(evt)

        data["events"] = events
        n = len(events)
        n_sess = sum(len(e.get("sessions", [])) for e in events)
        self._progress(f"✅ Done: {n} events, {n_sess} sessions total")
        return data

    def _fix_event_dates(self, evt: Dict):
        """Recalculate end_date from session dates if sessions span multiple days."""
        sessions = evt.get("sessions", [])
        if not sessions:
            return

        all_dates = set()
        start_str = evt.get("start_date", "")
        if start_str:
            all_dates.add(start_str[:10])

        for s in sessions:
            # Extract date from session start time
            s_start = s.get("start") or ""
            if s_start and len(str(s_start)) >= 10:
                sess_date = str(s_start)[:10]
                all_dates.add(sess_date)

        if all_dates:
            sorted_dates = sorted(all_dates)
            evt["start_date"] = sorted_dates[0]
            evt["end_date"] = sorted_dates[-1]

    def _fetch_detail_sessions(self, url: str) -> List[Dict]:
        """Fetch session data from an event detail page."""
        # Try network capture first
        if self.playwright_enabled:
            try:
                from browser_client import capture_json_responses
                captured = self._run_async(
                    capture_json_responses(
                        url,
                        patterns=["session", "timetable", "programme", "race", "result"],
                        timeout_ms=20000
                    )
                )
                for resp in sorted(captured, key=lambda r: len(r.body), reverse=True):
                    try:
                        body = json.loads(resp.body)
                        sessions = self._extract_sessions_from_json(body)
                        if sessions:
                            return sessions
                    except (json.JSONDecodeError, TypeError):
                        continue
            except Exception as exc:
                logger.warning("Network capture for detail page failed: %s", exc)

        # Fall back to inline JSON
        try:
            html = self._fetch_html(url)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Check __NEXT_DATA__
            tag = soup.find("script", id="__NEXT_DATA__")
            if tag and tag.string:
                data = json.loads(tag.string)
                sessions = self._extract_sessions_from_json(data)
                if sessions:
                    return sessions

            # Scan all scripts
            for script in soup.find_all("script"):
                if script.string and '"session" ' in script.string.lower():
                    try:
                        parsed = json.loads(script.string.strip())
                        sessions = self._extract_sessions_from_json(parsed)
                        if sessions:
                            return sessions
                    except (json.JSONDecodeError, ValueError):
                        pass
        except Exception as exc:
            logger.warning("Inline JSON for detail page failed: %s", exc)

        return []

    def _extract_sessions_from_json(self, data: Any) -> List[Dict]:
        """Find and parse sessions from any JSON structure."""
        raw_sessions = self._deep_find_sessions(data)
        if not raw_sessions:
            return []
        sessions = []
        for s in raw_sessions:
            if isinstance(s, dict):
                parsed = self._parse_session_dict(s)
                if parsed:
                    sessions.append(parsed)
        return sessions

    def _deep_find_sessions(self, obj: Any, depth: int = 0) -> List:
        """Recursively find session-like arrays in JSON."""
        if depth > 8:
            return []

        if isinstance(obj, list) and len(obj) > 0:
            sample = obj[0] if isinstance(obj[0], dict) else {}
            keys_lower = {k.lower() for k in sample.keys()}
            if any(k in keys_lower for k in [
                "sessionname", "session_name", "sessiontype", "sessiondate",
                "sessionstarttime", "starttime", "session_start_time",
            ]):
                return obj

        if isinstance(obj, dict):
            # Check known session container keys first
            for key in ["sessions", "Sessions", "SessionResults", "sessionResults",
                        "session_results", "timetable", "programme"]:
                if key in obj:
                    val = obj[key]
                    if isinstance(val, list) and len(val) > 0:
                        sample = val[0] if isinstance(val[0], dict) else {}
                        keys_lower = {k.lower() for k in sample.keys()}
                        if any(k in keys_lower for k in [
                            "sessionname", "session_name", "name", "starttime",
                            "sessiontype", "sessiondate",
                        ]):
                            return val

            # Recurse into values
            for key, val in obj.items():
                result = self._deep_find_sessions(val, depth + 1)
                if result:
                    return result

        return []

    # =====================================================================
    # TIER 1: Inline JSON extraction
    # =====================================================================

    def _try_inline_json(self, html: str, series_name: str, season: int, hint: Optional[SiteHint] = None) -> Optional[Dict]:
        """Extract schedule from embedded JSON in the HTML."""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            self._progress("⚠️ bs4 not installed, skipping inline extraction")
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Strategy 1: __NEXT_DATA__ (Next.js — F1, F2, F3)
        next_tag = soup.find("script", id="__NEXT_DATA__")
        if next_tag and next_tag.string:
            self._progress("📦 Found __NEXT_DATA__ — parsing Next.js data...")
            try:
                data = json.loads(next_tag.string)
                result = self._parse_nextjs_data(data, series_name, season)
                if result and result.get("events"):
                    return result
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse __NEXT_DATA__: %s", e)

        # Strategy 2: Nuxt.js
        for script_id in ["__NUXT_DATA__", "__NUXT__"]:
            tag = soup.find("script", id=script_id)
            if tag and tag.string:
                self._progress(f"📦 Found {script_id}...")
                try:
                    data = json.loads(tag.string)
                    result = self._parse_generic_json(data, series_name, season, hint)
                    if result and result.get("events"):
                        return result
                except Exception:
                    pass

        # Strategy 3: Scan script tags for JSON data
        self._progress("🔍 Scanning scripts for race data...")
        for script_tag in soup.find_all("script"):
            if not script_tag.string:
                continue
            text = script_tag.string
            for pattern in [
                r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\});',
                r'window\.__DATA__\s*=\s*(\{.+?\});',
                r'window\.__PRELOADED_STATE__\s*=\s*(\{.+?\});',
            ]:
                for match in re.finditer(pattern, text, re.DOTALL):
                    try:
                        parsed = json.loads(match.group(1))
                        result = self._parse_generic_json(parsed, series_name, season, hint)
                        if result and result.get("events"):
                            self._progress("📦 Found data in inline script!")
                            return result
                    except (json.JSONDecodeError, IndexError):
                        continue

            # Try whole script as JSON
            stripped = text.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    result = self._parse_generic_json(parsed, series_name, season, hint)
                    if result and result.get("events"):
                        self._progress("📦 Found data in JSON script!")
                        return result
                except (json.JSONDecodeError, ValueError):
                    pass

        return None

    def _parse_nextjs_data(self, data: Dict, series_name: str, season: int, hint: Optional[SiteHint] = None) -> Optional[Dict]:
        """Parse Next.js __NEXT_DATA__."""
        page_data = (
            data.get("props", {})
                .get("pageProps", {})
                .get("pageData", {})
        )
        if not page_data:
            page_data = data.get("props", {}).get("pageProps", {})

        races = (
            page_data.get("Races") or page_data.get("races") or
            page_data.get("Events") or page_data.get("events") or
            page_data.get("Content", {}).get("Races") or []
        )
        if not races:
            races = self._deep_find_races(page_data, hint=hint)
        if not races:
            return None

        self._progress(f"📋 Found {len(races)} races in Next.js data")
        return self._parse_races_array(races, series_name, season)

    def _deep_find_races(self, obj: Any, depth: int = 0, hint: Optional[SiteHint] = None) -> List:
        """Find arrays of race-like objects."""
        if depth > 5:
            return []
        if isinstance(obj, list) and len(obj) > 0:
            sample = obj[0] if isinstance(obj[0], dict) else {}
            keys_lower = {k.lower() for k in sample.keys()}
            # Hints specific keys
            if hint and hint.json_keys.get("name") and hint.json_keys.get("start"):
                name_keys = {k.lower() for k in hint.json_keys["name"]}
                start_keys = {k.lower() for k in hint.json_keys["start"]}
                if any(k in keys_lower for k in name_keys) and any(k in keys_lower for k in start_keys):
                    return obj

            # F1/F2/F3 keys
            if any(k in keys_lower for k in [
                "raceid", "roundnumber", "racestartdate", "circuitname",
                "raceenddate", "sessions", "circuitshortname",
            ]):
                return obj
            # Formula E / generic keys
            if any(k in keys_lower for k in [
                "sequence", "circuit", "hasraceresults", "raceliveStatus",
            ]) and any(k in keys_lower for k in ["name", "date", "city", "country"]):
                return obj
        if isinstance(obj, dict):
            for key, val in obj.items():
                result = self._deep_find_races(val, depth + 1, hint)
                if result:
                    return result
        return []

    # =====================================================================
    # TIER 2: Network capture
    # =====================================================================

    def _try_network_capture(self, url: str, series_name: str, season: int, hint: Optional[SiteHint] = None) -> Optional[Dict]:
        """Intercept JSON API responses via Playwright."""
        if not self.playwright_enabled:
            self._progress("⚠️ Playwright disabled, skipping network capture")
            return None
        
        patterns = _CALENDAR_PATTERNS
        if hint and hint.network_patterns:
            patterns = hint.network_patterns + _CALENDAR_PATTERNS

        try:
            from browser_client import capture_json_responses
            captured = self._run_async(
                capture_json_responses(url, patterns=patterns, timeout_ms=30000)
            )
        except Exception as exc:
            self._progress(f"⚠️ Network capture failed: {exc}")
            return None

        if not captured:
            self._progress("📭 No matching API responses captured")
            return None

        self._progress(f"📡 Captured {len(captured)} responses — analyzing...")

        # Sort by size (largest first — likely has the most data)
        for resp in sorted(captured, key=lambda r: len(r.body), reverse=True):
            try:
                body = json.loads(resp.body)
                result = self._parse_generic_json(body, series_name, season, hint)
                if result and result.get("events"):
                    self._progress(f"🎯 Found schedule from: {resp.url[:80]}")
                    return result
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    # =====================================================================
    # TIER 3 & 4: AI extraction
    # =====================================================================

    def _try_ai_single(self, html: str, series_name: str, season: int, hint: Optional[SiteHint] = None) -> Optional[Dict]:
        try:
            from ai.vertex_extractor import DynamicExtractor
            context = hint.ai_context if hint else None
            return DynamicExtractor().extract(html, series_name, season, site_context=context)
        except Exception as exc:
            self._progress(f"⚠️ AI extraction failed: {exc}")
            return None

    def _try_ai_two_phase(self, html: str, url: str, series_name: str, season: int, hint: Optional[SiteHint] = None) -> Optional[Dict]:
        try:
            from ai.vertex_extractor import DynamicExtractor
            extractor = DynamicExtractor()
            context = hint.ai_context if hint else None
            events = extractor.extract_calendar(html, series_name, season, url, site_context=context)
            if not events:
                return None
            with_links = [e for e in events if e.get("url")]
            if with_links:
                self._progress(f"🏎️ Visiting {len(with_links)} event pages...")
                for i, evt in enumerate(with_links, 1):
                    try:
                        if i > 1:
                            time.sleep(2)
                        detail_html = self._fetch_html(evt["url"])
                        evt["sessions"] = extractor.extract_sessions(
                            detail_html, evt.get("name", f"E{i}"), series_name, season
                        )
                    except Exception:
                        evt["sessions"] = []
            for evt in events:
                evt.setdefault("sessions", [])
            sid = re.sub(r"[^a-z0-9]+", "_", series_name.lower()).strip("_")
            return {"series_id": sid, "name": series_name, "season": season, "events": events}
        except Exception as exc:
            self._progress(f"⚠️ AI two-phase failed: {exc}")
            return None

    # =====================================================================
    # Universal JSON parsers
    # =====================================================================

    def _parse_generic_json(self, data: Any, series_name: str, season: int, hint: Optional[SiteHint] = None) -> Optional[Dict]:
        """Parse any JSON that might contain race/event data."""
        races = None

        if isinstance(data, list) and len(data) > 0:
            sample = data[0] if isinstance(data[0], dict) else {}
            keys_lower = {k.lower() for k in sample.keys()}
            has_race_keys = any(k in keys_lower for k in [
                "raceid", "roundnumber", "racestartdate", "start_date",
                "circuitname", "sessions", "date_start",
                "sequence", "hasraceresults", "raceliveStatus",
            ])
            has_name_or_date = any(k in keys_lower for k in ["name", "date", "city"])
            if has_race_keys or (has_name_or_date and len(data) > 1):
                races = data

        elif isinstance(data, dict):
            for key in ["Races", "races", "Events", "events", "Calendar", "calendar",
                        "Meetings", "meetings", "rounds", "Rounds"]:
                if key in data and isinstance(data[key], list) and len(data[key]) > 0:
                    races = data[key]
                    break
            if not races:
                races = self._deep_find_races(data)

        if not races:
            return None

        return self._parse_races_array(races, series_name, season)

    def _parse_races_array(self, races: List[Dict], series_name: str, season: int) -> Dict:
        """Convert list of race dicts to standard format."""
        events = []
        for race in races:
            if not isinstance(race, dict):
                continue
            evt = self._parse_race_dict(race, series_name)
            if evt:
                events.append(evt)
        sid = re.sub(r"[^a-z0-9]+", "_", series_name.lower()).strip("_")
        return {"series_id": sid, "name": series_name, "season": season, "events": events}

    def _parse_race_dict(self, race: Dict, series_name: str) -> Optional[Dict]:
        """Parse a single race — handles F1/F2/F3, Formula E, MotoGP, generic."""
        r = {k.lower(): v for k, v in race.items()}

        # ── Name ──────────────────────────────────────────────────────
        name = (
            r.get("circuitshortname") or r.get("racename") or r.get("name")
            or r.get("circuitname") or r.get("meeting_name") or "Unknown"
        )

        # ── Dates ─────────────────────────────────────────────────────
        start = (r.get("racestartdate") or r.get("start_date") or r.get("date_start")
                 or r.get("date"))
        end = (r.get("raceenddate") or r.get("end_date") or r.get("date_end") or start)
        if not start:
            return None

        # ── Venue ─────────────────────────────────────────────────────
        circuit_raw = r.get("circuit")
        if isinstance(circuit_raw, dict):
            circuit = circuit_raw.get("circuitName", circuit_raw.get("name", ""))
        else:
            circuit = r.get("circuitname") or r.get("circuit_name") or str(circuit_raw or "")

        city = r.get("circuitshortname") or r.get("city") or r.get("place") or ""
        country = r.get("countryname") or r.get("country") or ""
        country_code = r.get("countrycode") or ""

        # If country is a 2-letter code, use it as country_code
        if len(country) == 2 and country.isupper():
            country_code = country
            country = ""

        tz = self._tz_from_country(country_code or country or city)

        # ── Round ─────────────────────────────────────────────────────
        round_num = r.get("roundnumber") or r.get("round") or r.get("sequence") or 0

        # ── Detail URL ────────────────────────────────────────────────
        detail_url = None
        metadata = r.get("metadata", {})
        if isinstance(metadata, dict):
            race_path = metadata.get("racePath") or metadata.get("eventPath") or ""
            if race_path:
                # Build full URL from the base site
                base = re.match(r"(https?://[^/]+)", self._target_url or "")
                if base:
                    detail_url = urljoin(base.group(1), race_path)

        # Also check for explicit URL fields
        if not detail_url:
            detail_url = r.get("url") or r.get("detail_url") or r.get("link") or None

        # ── Has results (for filtering) ───────────────────────────────
        has_results = r.get("hasraceresults") or r.get("has_results") or False

        # ── Sessions ──────────────────────────────────────────────────
        sessions = []
        raw_sessions = (
            r.get("sessions") or r.get("sessionresults") or
            r.get("session_results") or []
        )
        for sess in raw_sessions:
            if isinstance(sess, dict):
                parsed = self._parse_session_dict(sess)
                if parsed:
                    sessions.append(parsed)

        sid = re.sub(r"[^a-z0-9]+", "_", series_name.lower()).strip("_")
        return {
            "event_id": f"{sid}_{round_num}",
            "name": name,
            "start_date": str(start)[:10],
            "end_date": str(end)[:10] if end else str(start)[:10],
            "round_number": round_num,
            "has_results": has_results,
            "detail_url": detail_url,
            "venue": {
                "circuit": circuit or city or name,
                "city": city,
                "country": country or country_code,
                "timezone": tz,
            },
            "sessions": sessions,
        }

    def _parse_session_dict(self, sess: Dict) -> Optional[Dict]:
        """Parse a session — handles F1/F2/F3, Formula E, generic formats."""
        s = {k.lower(): v for k, v in sess.items()}

        name = s.get("sessionname") or s.get("name") or s.get("session_name") or ""
        short_name = s.get("sessionshortname") or s.get("shortname") or ""
        stype = (s.get("sessiontype") or s.get("type") or s.get("sessioncode") or "").upper()

        # ── Build timestamps ──────────────────────────────────────────
        # Format A: full ISO timestamps (F1/F2/F3)
        start = (s.get("sessionstarttime") or s.get("start_time") or s.get("start")
                 or s.get("session_start_time"))
        end = (s.get("sessionendtime") or s.get("end_time") or s.get("end")
               or s.get("session_end_time"))

        # Format B: separate date + time + offset (Formula E)
        # API has two sets of times: regular and contingency.
        # The website shows: regular startTime + contingencyFinishTime.
        # All times are UTC — add offset to get LOCAL track time.
        if not start and s.get("sessiondate") and s.get("starttime"):
            sess_date = s["sessiondate"]
            start_time_str = s["starttime"]
            # End time: prefer contingency (matches website display)
            finish_time_str = (s.get("contingencyfinishtime")
                               or s.get("finishtime") or s.get("endtime"))
            offset_str = s.get("offsetgmt", "00:00")

            # Convert UTC time to local: add offset
            start = self._utc_to_local_iso(sess_date, start_time_str, offset_str)
            if finish_time_str:
                end = self._utc_to_local_iso(sess_date, finish_time_str, offset_str)

        if not name and not start:
            return None

        # ── Determine type from name ──────────────────────────────────
        final_type = stype or "OTHER"
        name_upper = (name or "").upper()
        short_upper = (short_name or "").upper()

        if "FREE PRACTICE" in name_upper or "PRACTICE" in name_upper or "PRAC" in short_upper:
            final_type = "PRACTICE"
        elif "QUALIFYING" in name_upper or "QUAL" in short_upper or "QUAL" in name_upper:
            final_type = "QUALIFYING"
        elif "SPRINT" in name_upper or short_upper == "SR":
            final_type = "SPRINT"
        elif "FEATURE" in name_upper or short_upper == "FR":
            final_type = "RACE"
        elif "RACE" in name_upper or stype == "RESULT":
            final_type = "RACE"
        elif "WARM" in name_upper:
            final_type = "WARMUP"

        # ── Filter: skip non-essential sessions ──────────────────────
        # Keep only main sessions: Practice, Qualifying, Sprint, Race
        _KEEP_TYPES = {"PRACTICE", "QUALIFYING", "RACE", "SPRINT", "FEATURE"}
        if final_type not in _KEEP_TYPES:
            return None

        # ── Status ────────────────────────────────────────────────────
        status = (s.get("sessionlivestatus") or s.get("status") or "SCHEDULED").upper()

        return {
            "session_id": s.get("id") or s.get("sessionid") or "",
            "name": name or short_name or final_type,
            "type": final_type,
            "start": start,
            "end": end,
            "status": status,
        }

    @staticmethod
    def _tz_from_country(code: str) -> str:
        try:
            from validators.timezone_utils import infer_timezone_from_location
            result = infer_timezone_from_location(country=code)
            if result and isinstance(result, tuple):
                return result[0] or "UTC"
            if result:
                return str(result)
        except Exception:
            pass
        return "UTC"

    @staticmethod
    def _utc_to_local_iso(sess_date: str, utc_time: str, offset_str: str) -> str:
        """
        Convert UTC time to local ISO timestamp.

        Formula E API returns times in UTC with a separate offset.
        E.g. startTime="16:30", offsetGMT="01:00" → local 17:30.
        Returns: "2026-03-20T17:30:00+01:00"
        """
        try:
            # Parse offset "HH:MM" → timedelta
            parts = offset_str.split(":")
            offset_h = int(parts[0])
            offset_m = int(parts[1]) if len(parts) > 1 else 0
            offset_td = timedelta(hours=offset_h, minutes=offset_m)

            # Parse UTC time
            time_parts = utc_time.split(":")
            utc_h = int(time_parts[0])
            utc_m = int(time_parts[1]) if len(time_parts) > 1 else 0

            # Build UTC datetime, add offset to get local
            utc_dt = datetime.strptime(f"{sess_date} {utc_h:02d}:{utc_m:02d}", "%Y-%m-%d %H:%M")
            local_dt = utc_dt + offset_td

            # Format as ISO with offset: "2026-03-20T17:30:00+01:00"
            sign = "+"
            return f"{local_dt.strftime('%Y-%m-%dT%H:%M:%S')}{sign}{offset_h:02d}:{offset_m:02d}"
        except Exception:
            # Fallback: just combine without conversion
            return f"{sess_date}T{utc_time}:00+{offset_str}"

    # =====================================================================
    # Extract (JSON → Event objects)
    # =====================================================================

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        """Convert extracted JSON data to Event objects."""
        data = json.loads(raw.content)
        events: List[Event] = []
        for evt_data in data.get("events", []):
            try:
                events.append(self._build_event(evt_data, raw))
            except Exception as exc:
                logger.warning("Skipping event %s: %s", evt_data.get("name", "?"), exc)
        logger.info("Built %d Event objects", len(events))
        return events

    # =====================================================================
    # Helpers
    # =====================================================================

    def _pack(self, data: Dict, url: str, series_id: str,
              season: int, method: str) -> RawSeriesPayload:
        return RawSeriesPayload(
            content=json.dumps(data, default=str),
            content_type="application/json",
            url=url,
            retrieved_at=datetime.utcnow(),
            metadata={
                "series_id": series_id,
                "season": season,
                "extraction_method": f"dynamic_{method}",
                "events_found": len(data.get("events", [])),
            },
        )

    def _fetch_html(self, url: str) -> str:
        """Render page; fall back to httpx."""
        if self.playwright_enabled:
            try:
                rendered = self._run_async(self._playwright_get(url, timeout=45.0))
                return rendered.content
            except Exception as exc:
                logger.warning("Playwright failed for %s: %s", url, exc)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = self._http_get(url, timeout=30.0, headers=headers)
        return resp.text

    def _build_event(self, d: Dict[str, Any], raw: RawSeriesPayload) -> Event:
        venue_data = d.get("venue", {})
        venue = Venue(
            circuit=venue_data.get("circuit"),
            city=venue_data.get("city"),
            region=venue_data.get("region"),
            country=venue_data.get("country", "Unknown"),
            timezone=venue_data.get("timezone", "UTC"),
        )
        sessions = self._build_sessions(d.get("sessions", []))
        source = self.create_source(
            url=d.get("detail_url", raw.url),
            retrieved_at=raw.retrieved_at,
            extraction_method=raw.metadata.get("extraction_method", "dynamic_ai"),
        )
        series_id = d.get("series_id", raw.metadata.get("series_id", "unknown"))
        return Event(
            event_id=d.get("event_id", f"{series_id}_{self._slugify(d.get('name', ''))}"),
            series_id=series_id,
            name=d.get("name", "Unknown Event"),
            start_date=self._parse_date(d.get("start_date")),
            end_date=self._parse_date(d.get("end_date", d.get("start_date"))),
            venue=venue,
            sessions=sessions,
            sources=[source],
        )

    def _build_sessions(self, items: List[Dict[str, Any]]) -> List[Session]:
        sessions: List[Session] = []
        for i, s in enumerate(items):
            try:
                stype_str = (s.get("type") or "OTHER").upper()
                stype = _SESSION_TYPE_MAP.get(stype_str, SessionType.OTHER)
                sstatus_str = (s.get("status") or "SCHEDULED").upper()
                sstatus = _SESSION_STATUS_MAP.get(sstatus_str, SessionStatus.SCHEDULED)
                sessions.append(Session(
                    session_id=s.get("session_id") or f"s{i+1}",
                    type=stype,
                    name=s.get("name", f"Session {i+1}"),
                    start=s.get("start"),
                    end=s.get("end"),
                    status=sstatus,
                ))
            except Exception as exc:
                logger.warning("Skipping session: %s", exc)
        return sessions

    @staticmethod
    def _parse_date(value) -> date:
        if value is None:
            return date.today()
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return date.today()

    @staticmethod
    def _slugify(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:50]
