"""
Generic Web Connector — Playwright-based scraper for any motorsport website.

Uses Playwright to load JS-rendered pages, captures network JSON endpoints,
and falls back to DOM scraping for schedule/event/session extraction.
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date
import re
import json
from .base import Connector, RawSeriesPayload
from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SessionType, SessionStatus, SeriesCategory
from validators.timezone_utils import infer_timezone_from_location


class GenericWebConnector(Connector):
    """
    Dynamic connector for any motorsport website.

    Configure with series metadata, then set a target URL before fetching.
    Uses Playwright for JS-rendered SPAs with two-pass extraction:
      1. Network capture — look for JSON API endpoints with schedule data
      2. DOM scraping — parse rendered HTML for events/sessions
    """

    def __init__(self, series_configs: Dict[str, Dict[str, Any]]):
        """
        Args:
            series_configs: Dict mapping series_id -> {name, category}
                e.g. {"dtm": {"name": "DTM", "category": SeriesCategory.GT}}
        """
        super().__init__()
        self._series_configs = series_configs
        self._target_url: Optional[str] = None

    @property
    def id(self) -> str:
        return "generic_web"

    @property
    def name(self) -> str:
        return "Generic Web Scraper"

    @property
    def needs_url(self) -> bool:
        """Indicates this connector requires a user-provided URL."""
        return True

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id=sid,
                name=cfg["name"],
                category=cfg["category"],
                connector_id=self.id,
            )
            for sid, cfg in self._series_configs.items()
        ]

    def set_target_url(self, url: str):
        """Set the URL to scrape before calling fetch_season."""
        self._target_url = url.strip()

    # ------------------------------------------------------------------
    # fetch
    # ------------------------------------------------------------------

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if not self._target_url:
            raise ValueError(
                "No target URL set. Paste the schedule page URL in the UI."
            )

        if series_id not in self._series_configs:
            raise ValueError(f"Unsupported series: {series_id}")

        cached = self._get_from_cache(series_id, season)
        if cached:
            return cached

        # -- Step 1: Capture network JSON responses via Playwright --
        captured_json: List[Dict[str, Any]] = []
        try:
            captured = self._run_async(
                self._capture_endpoints(
                    self._target_url,
                    patterns=[
                        "schedule", "calendar", "event", "race",
                        "season", "round", "session", "timetable",
                    ],
                )
            )
            captured_json = [
                {
                    "url": c.url,
                    "body": c.body,
                    "content_type": c.content_type,
                }
                for c in captured
            ]
        except Exception as e:
            # Log but continue — will fall back to HTTP
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Network capture failed for {self._target_url}: {e}")

        # -- Step 2: Get rendered DOM --
        html_content = ""
        try:
            rendered = self._run_async(
                self._playwright_get(self._target_url, timeout=45.0)
            )
            html_content = rendered.content
        except Exception as e:
            # Log Playwright failure, try HTTP fallback
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Playwright rendering failed for {self._target_url}: {e}")
            
            try:
                response = self._http_get(self._target_url, timeout=30.0)
                html_content = response.text
                logger.info(f"HTTP fallback succeeded for {self._target_url}")
            except Exception as http_error:
                logger.error(f"HTTP fallback also failed for {self._target_url}: {http_error}")
                raise RuntimeError(
                    f"Failed to fetch {self._target_url} via Playwright and HTTP: {e}"
                )

        payload = RawSeriesPayload(
            content=html_content,
            content_type="text/html",
            url=self._target_url,
            retrieved_at=datetime.utcnow(),
            metadata={
                "season": season,
                "series_id": series_id,
                "captured_responses": captured_json,
            },
        )

        self._save_to_cache(series_id, season, payload)
        return payload

    # ------------------------------------------------------------------
    # extract
    # ------------------------------------------------------------------

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        season = raw.metadata.get("season", datetime.now().year)
        series_id = raw.metadata.get("series_id", "unknown")
        captured = raw.metadata.get("captured_responses", [])

        events: List[Event] = []

        # Pass 1: Try to extract from captured JSON endpoints
        if captured:
            events = self._extract_from_json(captured, series_id, season, raw)

        # Pass 2: Fall back to DOM scraping
        if not events and raw.content:
            events = self._extract_from_dom(raw.content, series_id, season, raw)

        events.sort(key=lambda e: e.start_date)
        return events

    # ------------------------------------------------------------------
    # JSON extraction — parse captured API responses
    # ------------------------------------------------------------------

    def _extract_from_json(
        self,
        captured: List[Dict[str, Any]],
        series_id: str,
        season: int,
        raw: RawSeriesPayload,
    ) -> List[Event]:
        """Try to extract events from captured JSON network responses."""
        events: List[Event] = []

        for resp in captured:
            body = resp.get("body", "")
            if not body:
                continue
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                continue

            # Try various JSON shapes
            found = self._parse_json_data(data, series_id, season, raw)
            events.extend(found)

        return events

    def _parse_json_data(
        self,
        data: Any,
        series_id: str,
        season: int,
        raw: RawSeriesPayload,
    ) -> List[Event]:
        """
        Attempt to parse schedule data from arbitrary JSON.

        Looks for common patterns:
        - List of objects with date/name/venue fields
        - Nested structure with "events", "races", "schedule", etc.
        """
        events: List[Event] = []

        # If it's a list, check items directly
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    event = self._try_parse_event_dict(
                        item, series_id, season, raw
                    )
                    if event:
                        events.append(event)
            if events:
                return events

        # If it's a dict, look for nested arrays
        if isinstance(data, dict):
            # Look for common container keys
            for key in [
                "events", "races", "schedule", "rounds",
                "calendar", "data", "items", "results",
                "content", "entries", "meetings",
            ]:
                if key in data and isinstance(data[key], list):
                    for item in data[key]:
                        if isinstance(item, dict):
                            event = self._try_parse_event_dict(
                                item, series_id, season, raw
                            )
                            if event:
                                events.append(event)
                    if events:
                        return events

            # Recurse one level into dict values
            for val in data.values():
                if isinstance(val, dict):
                    found = self._parse_json_data(val, series_id, season, raw)
                    if found:
                        return found

        return events

    def _try_parse_event_dict(
        self,
        item: Dict[str, Any],
        series_id: str,
        season: int,
        raw: RawSeriesPayload,
    ) -> Optional[Event]:
        """Try to parse a dict as an Event."""
        # Find event name
        name = None
        for key in ["name", "title", "eventName", "event_name",
                     "race_name", "raceName", "label", "heading"]:
            if key in item and isinstance(item[key], str) and item[key].strip():
                name = item[key].strip()
                break

        if not name:
            return None

        # Find dates
        start_date = None
        end_date = None
        for key in ["start_date", "startDate", "date", "from",
                     "start", "dateFrom", "date_start"]:
            if key in item:
                start_date = self._parse_date_from_value(item[key], season)
                if start_date:
                    break

        for key in ["end_date", "endDate", "dateTo", "to",
                     "end", "date_end"]:
            if key in item:
                end_date = self._parse_date_from_value(item[key], season)
                if end_date:
                    break

        if not start_date:
            # Try generic "date" field
            for key in ["date", "datetime"]:
                if key in item:
                    start_date = self._parse_date_from_value(item[key], season)
                    if start_date:
                        break

        if not start_date:
            return None

        if not end_date:
            end_date = start_date

        # Find venue info
        venue = self._extract_venue_from_dict(item)

        # Find sessions
        sessions = self._extract_sessions_from_dict(item, season)

        # Build event ID
        event_id = self._generate_event_id(name, series_id, season)

        source = self.create_source(raw.url, raw.retrieved_at)

        return Event(
            event_id=event_id,
            series_id=series_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            venue=venue,
            sessions=sessions,
            sources=[source],
            last_verified_at=raw.retrieved_at,
        )

    def _parse_date_from_value(self, value: Any, season: int) -> Optional[date]:
        """Parse a date from various formats."""
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None

        value = value.strip()
        if not value:
            return None

        # ISO format: 2026-04-25 or 2026-04-25T14:00:00
        iso_match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
        if iso_match:
            try:
                return date(
                    int(iso_match.group(1)),
                    int(iso_match.group(2)),
                    int(iso_match.group(3)),
                )
            except ValueError:
                pass

        # European format: 25.04.2026 or 25/04/2026
        eu_match = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", value)
        if eu_match:
            try:
                return date(
                    int(eu_match.group(3)),
                    int(eu_match.group(2)),
                    int(eu_match.group(1)),
                )
            except ValueError:
                pass

        # Text format: "April 25, 2026" or "25 April 2026"
        for fmt in ["%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y",
                     "%B %d %Y", "%d/%m/%Y", "%m/%d/%Y"]:
            try:
                return datetime.strptime(value[:20], fmt).date()
            except ValueError:
                continue

        # Partial date with season: "April 25" or "25 April"
        for fmt in ["%B %d", "%d %B", "%b %d", "%d %b"]:
            try:
                parsed = datetime.strptime(value.strip(), fmt)
                return date(season, parsed.month, parsed.day)
            except ValueError:
                continue

        return None

    def _extract_venue_from_dict(self, item: Dict[str, Any]) -> Venue:
        """Extract venue information from a JSON dict."""
        circuit = None
        city = None
        country = None
        region = None

        # Circuit/track name
        for key in ["circuit", "track", "trackName", "circuit_name",
                     "venue", "venueName", "track_name", "circuitName"]:
            if key in item and isinstance(item[key], str):
                circuit = item[key].strip()
                break

        # Nested venue/circuit object
        for key in ["venue", "circuit", "track", "location"]:
            if key in item and isinstance(item[key], dict):
                nested = item[key]
                if not circuit:
                    for nk in ["name", "circuit", "track", "circuitName", "trackName"]:
                        if nk in nested and isinstance(nested[nk], str):
                            circuit = nested[nk].strip()
                            break
                if not city:
                    city = nested.get("city") or nested.get("town")
                if not country:
                    country = nested.get("country") or nested.get("countryName")
                if not region:
                    region = nested.get("region") or nested.get("state")

        # Top-level location fields
        if not city:
            for key in ["city", "location", "town"]:
                if key in item and isinstance(item[key], str):
                    city = item[key].strip()
                    break
        if not country:
            for key in ["country", "countryName", "country_name"]:
                if key in item and isinstance(item[key], str):
                    country = item[key].strip()
                    break

        if not country:
            country = "Unknown"

        timezone, inferred = infer_timezone_from_location(
            country=country, city=city
        )
        if not timezone:
            timezone = "UTC"
            inferred = True

        return Venue(
            circuit=circuit,
            city=city,
            region=region,
            country=country,
            timezone=timezone,
            inferred_timezone=inferred,
        )

    def _extract_sessions_from_dict(
        self, item: Dict[str, Any], season: int
    ) -> List[Session]:
        """Extract sessions from a JSON event dict."""
        sessions: List[Session] = []

        # Look for nested session arrays
        for key in ["sessions", "timetable", "schedule",
                     "programme", "program", "entries"]:
            if key in item and isinstance(item[key], list):
                for idx, s in enumerate(item[key]):
                    if isinstance(s, dict):
                        session = self._try_parse_session_dict(s, idx, season)
                        if session:
                            sessions.append(session)
                return sessions

        return sessions

    def _try_parse_session_dict(
        self, s: Dict[str, Any], idx: int, season: int
    ) -> Optional[Session]:
        """Try to parse a dict as a Session."""
        name = None
        for key in ["name", "title", "sessionName", "session_name",
                     "description", "type", "label"]:
            if key in s and isinstance(s[key], str) and s[key].strip():
                name = s[key].strip()
                break
        if not name:
            return None

        session_type = self._classify_session_type(name)
        session_id = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

        # Parse start/end times
        start_iso = None
        end_iso = None
        status = SessionStatus.TBD

        for key in ["start", "startDate", "start_time", "startTime",
                     "datetime", "date_time"]:
            if key in s and isinstance(s[key], str):
                try:
                    dt = datetime.fromisoformat(
                        s[key].replace("Z", "+00:00")
                    )
                    start_iso = dt.isoformat()
                    status = SessionStatus.SCHEDULED
                    break
                except (ValueError, TypeError):
                    pass

        for key in ["end", "endDate", "end_time", "endTime"]:
            if key in s and isinstance(s[key], str):
                try:
                    dt = datetime.fromisoformat(
                        s[key].replace("Z", "+00:00")
                    )
                    end_iso = dt.isoformat()
                    break
                except (ValueError, TypeError):
                    pass

        return Session(
            session_id=f"s{idx}_{session_id}",
            type=session_type,
            name=name,
            start=start_iso,
            end=end_iso,
            status=status,
        )

    # ------------------------------------------------------------------
    # DOM extraction — parse rendered HTML
    # ------------------------------------------------------------------

    def _extract_from_dom(
        self,
        html: str,
        series_id: str,
        season: int,
        raw: RawSeriesPayload,
    ) -> List[Event]:
        """Extract events from rendered HTML DOM."""
        try:
            from selectolax.parser import HTMLParser
        except ImportError:
            return []

        tree = HTMLParser(html)
        events: List[Event] = []

        # Strategy 1: Look for tables with date/event patterns
        events = self._extract_from_tables(tree, series_id, season, raw)
        if events:
            return events

        # Strategy 2: Look for card-style event elements
        events = self._extract_from_cards(tree, series_id, season, raw)
        if events:
            return events

        # Strategy 3: Look for list items with date patterns
        events = self._extract_from_lists(tree, series_id, season, raw)
        return events

    def _extract_from_tables(self, tree, series_id, season, raw) -> List[Event]:
        """Try to extract events from HTML tables."""
        events: List[Event] = []

        for table in tree.css("table"):
            rows = table.css("tr")
            for row in rows:
                cells = [td.text(strip=True) for td in row.css("td, th")]
                if len(cells) < 2:
                    continue

                # Look for rows that have a date-like and name-like cell
                event = self._try_row_as_event(cells, series_id, season, raw)
                if event:
                    events.append(event)

        return events

    def _extract_from_cards(self, tree, series_id, season, raw) -> List[Event]:
        """Try to extract events from card-style div elements."""
        events: List[Event] = []

        # Common card patterns
        card_selectors = [
            "[class*=event]", "[class*=race]", "[class*=round]",
            "[class*=card]", "[class*=schedule]",
            "article", ".item", ".entry",
        ]

        seen_names = set()
        for selector in card_selectors:
            for card in tree.css(selector):
                text = card.text(strip=True)
                if len(text) < 10 or len(text) > 2000:
                    continue

                # Try to find a name (first heading or strong text)
                name = None
                for heading in card.css("h1, h2, h3, h4, strong, b, .title, .name"):
                    name = heading.text(strip=True)
                    if name and len(name) > 3:
                        break

                if not name or name in seen_names:
                    continue

                # Try to find a date in the card text
                found_date = self._find_date_in_text(text, season)
                if not found_date:
                    continue

                seen_names.add(name)

                # Try to find location
                venue = self._find_venue_in_text(text)

                event_id = self._generate_event_id(name, series_id, season)
                source = self.create_source(raw.url, raw.retrieved_at)

                events.append(Event(
                    event_id=event_id,
                    series_id=series_id,
                    name=name,
                    start_date=found_date,
                    end_date=found_date,
                    venue=venue,
                    sessions=[],
                    sources=[source],
                    last_verified_at=raw.retrieved_at,
                ))

        return events

    def _extract_from_lists(self, tree, series_id, season, raw) -> List[Event]:
        """Try to extract from list items."""
        events: List[Event] = []

        for li in tree.css("li"):
            text = li.text(strip=True)
            if len(text) < 10 or len(text) > 500:
                continue

            found_date = self._find_date_in_text(text, season)
            if not found_date:
                continue

            # Use the text as name (trimmed)
            name = text[:80].strip()

            event_id = self._generate_event_id(name, series_id, season)
            source = self.create_source(raw.url, raw.retrieved_at)

            venue = self._find_venue_in_text(text)

            events.append(Event(
                event_id=event_id,
                series_id=series_id,
                name=name,
                start_date=found_date,
                end_date=found_date,
                venue=venue,
                sessions=[],
                sources=[source],
                last_verified_at=raw.retrieved_at,
            ))

        return events

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _try_row_as_event(
        self, cells: List[str], series_id: str, season: int, raw
    ) -> Optional[Event]:
        """Try to interpret a table row as an event."""
        name = None
        found_date = None

        for cell in cells:
            if not found_date:
                found_date = self._find_date_in_text(cell, season)
            if not name and len(cell) > 3 and not re.match(r"^\d", cell):
                name = cell

        if not name or not found_date:
            return None

        event_id = self._generate_event_id(name, series_id, season)
        source = self.create_source(raw.url, raw.retrieved_at)
        venue = self._find_venue_in_text(" ".join(cells))

        return Event(
            event_id=event_id,
            series_id=series_id,
            name=name,
            start_date=found_date,
            end_date=found_date,
            venue=venue,
            sessions=[],
            sources=[source],
            last_verified_at=raw.retrieved_at,
        )

    def _find_date_in_text(self, text: str, season: int) -> Optional[date]:
        """Find the first date-like pattern in text."""
        # ISO: 2026-04-25
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        # European: 25.04.2026 or 25/04/2026
        m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass

        # Text: "April 25" or "25 April" (with season year)
        m = re.search(
            r"([A-Z][a-z]{2,8})\s+(\d{1,2})", text
        )
        if m:
            for fmt in ["%B %d", "%b %d"]:
                try:
                    parsed = datetime.strptime(
                        f"{m.group(1)} {m.group(2)}", fmt
                    )
                    return date(season, parsed.month, parsed.day)
                except ValueError:
                    continue

        m = re.search(
            r"(\d{1,2})\s+([A-Z][a-z]{2,8})", text
        )
        if m:
            for fmt in ["%d %B", "%d %b"]:
                try:
                    parsed = datetime.strptime(
                        f"{m.group(1)} {m.group(2)}", fmt
                    )
                    return date(season, parsed.month, parsed.day)
                except ValueError:
                    continue

        return None

    def _find_venue_in_text(self, text: str) -> Venue:
        """Best-effort venue extraction from text."""
        # Default venue with UTC
        return Venue(
            circuit=None,
            city=None,
            country="Unknown",
            timezone="UTC",
            inferred_timezone=True,
        )

    def _classify_session_type(self, description: str) -> SessionType:
        """Classify session type from description text."""
        lower = description.lower()
        if "practice" in lower or "fp" in lower:
            return SessionType.PRACTICE
        elif "qual" in lower:
            return SessionType.QUALIFYING
        elif "race 1" in lower:
            return SessionType.RACE_1
        elif "race 2" in lower:
            return SessionType.RACE_2
        elif "race" in lower and "feature" not in lower:
            return SessionType.RACE
        elif "sprint" in lower:
            return SessionType.SPRINT
        elif "warmup" in lower or "warm up" in lower or "warm-up" in lower:
            return SessionType.WARMUP
        elif "test" in lower:
            return SessionType.TEST
        else:
            return SessionType.OTHER

    def _generate_event_id(self, name: str, series_id: str, season: int) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        return f"{series_id}_{season}_{slug}"
