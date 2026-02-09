"""
IndyCar connector — scrapes IndyCar.com schedule + event detail pages.
"""

from typing import List, Optional, Tuple
from datetime import datetime, date
import re
from selectolax.parser import HTMLParser
from .base import Connector, RawSeriesPayload
from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SessionType, SessionStatus, SeriesCategory
from validators.timezone_utils import infer_timezone_from_location


class IndyCarConnector(Connector):
    """Connector for IndyCar series — scrapes indycar.com official site."""

    BASE_URL = "https://www.indycar.com"
    SCHEDULE_URL = "https://www.indycar.com/schedule"

    @property
    def id(self) -> str:
        return "indycar_official"

    @property
    def name(self) -> str:
        return "IndyCar Official Website"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="indycar",
                name="NTT IndyCar Series",
                category=SeriesCategory.OPENWHEEL,
                connector_id=self.id,
            )
        ]

    # ------------------------------------------------------------------
    # fetch
    # ------------------------------------------------------------------

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "indycar":
            raise ValueError(f"Unsupported series: {series_id}")

        cached = self._get_from_cache(series_id, season)
        if cached:
            return cached

        response = self._http_get(self.SCHEDULE_URL)

        payload = RawSeriesPayload(
            content=response.text,
            content_type="text/html",
            url=self.SCHEDULE_URL,
            retrieved_at=datetime.utcnow(),
            metadata={"season": season},
        )

        self._save_to_cache(series_id, season, payload)
        return payload

    # ------------------------------------------------------------------
    # extract — list of events from main schedule page
    # ------------------------------------------------------------------

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        season = raw.metadata.get("season", datetime.now().year)
        tree = HTMLParser(raw.content)

        # --- Build slug → track_name mapping from event cards ---
        track_names: dict = {}
        for card in tree.css(".event-card-link, [class*=event-card]"):
            card_href = card.attributes.get("href", "")
            card_match = re.search(
                rf"/Schedule/{season}/([A-Za-z0-9\-]+)", card_href
            )
            if card_match:
                s = card_match.group(1)
                tn = card.css_first(".event-card-track-name")
                if tn:
                    track_names[s] = tn.text(strip=True)

        events: List[Event] = []
        seen_hrefs: set = set()

        # Find all event-detail links matching /Schedule/<year>/…
        for link in tree.css('a[href*="/Schedule/"]'):
            href = link.attributes.get("href", "")
            if not href:
                continue

            pattern = rf"/Schedule/{season}/([A-Za-z0-9\-]+)"
            match = re.search(pattern, href)
            if not match:
                continue

            slug = match.group(1)
            if slug in seen_hrefs:
                continue
            seen_hrefs.add(slug)

            detail_url = f"{self.BASE_URL}/Schedule/{season}/{slug}"
            circuit_name = track_names.get(slug)

            try:
                event = self._scrape_event_detail(
                    detail_url, slug, season, raw, circuit_name
                )
                if event:
                    events.append(event)
            except Exception:
                pass

        events.sort(key=lambda e: e.start_date)
        return events

    # ------------------------------------------------------------------
    # scrape individual event detail page
    # ------------------------------------------------------------------

    def _scrape_event_detail(
        self,
        url: str,
        slug: str,
        season: int,
        raw: RawSeriesPayload,
        circuit_name: Optional[str] = None,
    ) -> Optional[Event]:
        response = self._http_get(url)
        tree = HTMLParser(response.text)

        # --- Event name from <h1> ---
        h1 = tree.css_first("h1")
        event_name = h1.text(strip=True) if h1 else slug.replace("-", " ").title()

        # --- Date range & location from hero text ---
        date_range_text, location_text = self._parse_hero_info(tree, season)
        start_date, end_date = self._parse_date_range(date_range_text, season)

        # --- Sessions from schedule-table ---
        sessions = self._parse_sessions(tree, season, start_date)

        # --- Venue ---
        venue = self._build_venue(location_text, circuit_name)

        # --- Source ---
        source = self.create_source(url, raw.retrieved_at)

        event_id = self._generate_event_id(event_name, season)

        return Event(
            event_id=event_id,
            series_id="indycar",
            name=event_name,
            start_date=start_date,
            end_date=end_date,
            venue=venue,
            sessions=sessions,
            sources=[source],
            last_verified_at=raw.retrieved_at,
        )

    # ------------------------------------------------------------------
    # parsing helpers
    # ------------------------------------------------------------------

    def _parse_hero_info(
        self, tree: HTMLParser, season: int
    ) -> Tuple[str, str]:
        """
        Extract date-range string and location from the hero section.

        The hero text is formatted like:
            'February 27 - March 1 |St. Petersburg, Florida'
            'March 6 - 7 | Avondale, Arizona'
        Returns (date_range_text, location_text).
        """
        for node in tree.css("p, span, div"):
            text = node.text(strip=True)
            # Look for the pipe-separated pattern
            if "|" in text:
                parts = text.split("|", 1)
                left = parts[0].strip()
                right = parts[1].strip()
                # Validate left looks like a date range
                if re.search(r"[A-Z][a-z]+\s+\d", left) and "," in right:
                    return left, right
        return "", ""

    def _parse_date_range(
        self, text: str, season: int
    ) -> Tuple[date, date]:
        """Parse 'February 27 - March 1' or 'March 6 - 7' into (start, end)."""
        if not text:
            fallback = date(season, 1, 1)
            return fallback, fallback

        # Multi-month: "February 27 - March 1"
        m = re.match(
            r"([A-Z][a-z]+)\s+(\d{1,2})\s*[-–]\s*([A-Z][a-z]+)\s+(\d{1,2})",
            text,
        )
        if m:
            try:
                start = datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {season}", "%B %d %Y"
                ).date()
                end = datetime.strptime(
                    f"{m.group(3)} {m.group(4)} {season}", "%B %d %Y"
                ).date()
                return start, end
            except ValueError:
                pass

        # Same-month: "March 6 - 7"
        m2 = re.match(
            r"([A-Z][a-z]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2})",
            text,
        )
        if m2:
            try:
                start = datetime.strptime(
                    f"{m2.group(1)} {m2.group(2)} {season}", "%B %d %Y"
                ).date()
                end = datetime.strptime(
                    f"{m2.group(1)} {m2.group(3)} {season}", "%B %d %Y"
                ).date()
                return start, end
            except ValueError:
                pass

        # Single date: "March 6"
        m3 = re.match(r"([A-Z][a-z]+)\s+(\d{1,2})$", text.strip())
        if m3:
            try:
                d = datetime.strptime(
                    f"{m3.group(1)} {m3.group(2)} {season}", "%B %d %Y"
                ).date()
                return d, d
            except ValueError:
                pass

        fallback = date(season, 1, 1)
        return fallback, fallback

    def _parse_sessions(
        self,
        tree: HTMLParser,
        season: int,
        event_start: date,
    ) -> List[Session]:
        """Parse sessions from the .schedule-table section."""
        sessions: List[Session] = []

        schedule_table = tree.css_first(".schedule-table")
        if not schedule_table:
            return sessions

        current_day_text = ""
        current_date: Optional[date] = None

        for child in schedule_table.iter():
            # Day headers: <h3>Friday, Feb 27</h3>
            if child.tag == "h3":
                current_day_text = child.text(strip=True)
                current_date = self._parse_day_header(current_day_text, season)
                continue

            # Session entries
            if child.tag == "div" and child.attributes.get("class", "") and "schedule-entry" in child.attributes.get("class", ""):
                session = self._parse_session_entry(child, current_date, current_day_text)
                if session:
                    sessions.append(session)

        return sessions

    def _parse_day_header(self, text: str, season: int) -> Optional[date]:
        """Parse 'Friday, Feb 27' -> date."""
        # Remove day name
        m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2})", text)
        if m:
            month_str = m.group(1)
            day = int(m.group(2))
            try:
                return datetime.strptime(
                    f"{month_str} {day} {season}", "%b %d %Y"
                ).date()
            except ValueError:
                try:
                    return datetime.strptime(
                        f"{month_str} {day} {season}", "%B %d %Y"
                    ).date()
                except ValueError:
                    pass
        return None

    def _parse_session_entry(
        self,
        entry_node,
        session_date: Optional[date],
        day_text: str,
    ) -> Optional[Session]:
        """Parse a single .schedule-entry div into a Session."""
        # Get description (session name)
        desc_node = entry_node.css_first(".schedule-description")
        if not desc_node:
            return None

        full_desc = desc_node.text(strip=True)
        if not full_desc:
            return None

        # Get time
        time_node = entry_node.css_first(".schedule-time")
        time_text = time_node.text(strip=True) if time_node else ""

        # Parse time into ISO-8601 if available
        start_iso = None
        end_iso = None
        status = SessionStatus.TBD

        if time_text and session_date:
            parsed_time = self._parse_time_text(time_text)
            if parsed_time:
                hour, minute, tz_abbrev = parsed_time
                # Construct ISO datetime (use ET offset as default)
                offset = self._tz_abbrev_to_offset(tz_abbrev)
                dt = datetime(
                    session_date.year,
                    session_date.month,
                    session_date.day,
                    hour,
                    minute,
                )
                start_iso = dt.strftime(f"%Y-%m-%dT%H:%M:00{offset}")
                status = SessionStatus.SCHEDULED

        # Classify session type from description
        session_type = self._classify_session_type(full_desc)

        # Clean up the session name (remove "NTT INDYCAR SERIES – " prefix)
        session_name = self._clean_session_name(full_desc)

        # Generate session ID
        session_id = re.sub(r"[^a-z0-9]+", "_", full_desc.lower()).strip("_")

        return Session(
            session_id=session_id,
            type=session_type,
            name=session_name,
            start=start_iso,
            end=end_iso,
            status=status,
        )

    def _parse_time_text(self, text: str) -> Optional[Tuple[int, int, str]]:
        """Parse '4:30PM ET' -> (16, 30, 'ET')."""
        m = re.match(
            r"(\d{1,2}):(\d{2})\s*(AM|PM)\s*(ET|CT|MT|PT)?",
            text.strip(),
            re.IGNORECASE,
        )
        if not m:
            return None
        hour = int(m.group(1))
        minute = int(m.group(2))
        ampm = m.group(3).upper()
        tz = (m.group(4) or "ET").upper()

        if ampm == "PM" and hour != 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0

        return hour, minute, tz

    def _tz_abbrev_to_offset(self, abbrev: str) -> str:
        """Convert timezone abbreviation to UTC offset string."""
        offsets = {
            "ET": "-05:00",
            "CT": "-06:00",
            "MT": "-07:00",
            "PT": "-08:00",
            "EST": "-05:00",
            "CST": "-06:00",
            "MST": "-07:00",
            "PST": "-08:00",
            "EDT": "-04:00",
            "CDT": "-05:00",
            "MDT": "-06:00",
            "PDT": "-07:00",
        }
        return offsets.get(abbrev, "-05:00")

    def _classify_session_type(self, description: str) -> SessionType:
        """Classify session type from description text."""
        lower = description.lower()
        if "practice" in lower or "fp" in lower:
            return SessionType.PRACTICE
        elif "qual" in lower:
            return SessionType.QUALIFYING
        elif "race" in lower and "feature" not in lower:
            return SessionType.RACE
        elif "warmup" in lower or "warm up" in lower or "warm-up" in lower:
            return SessionType.WARMUP
        elif "test" in lower:
            return SessionType.TEST
        else:
            return SessionType.OTHER

    def _clean_session_name(self, full_desc: str) -> str:
        """Remove series prefix from session name."""
        # Patterns like "NTT INDYCAR SERIES – Practice 1" or "NTT INDYCAR SERIES - Race"
        cleaned = re.sub(
            r"^(NTT\s+)?INDYCAR\s+SERIES\s*[–\-]\s*",
            "",
            full_desc,
            flags=re.IGNORECASE,
        )
        return cleaned.strip() or full_desc

    def _build_venue(
        self, location_text: str, circuit_name: Optional[str] = None
    ) -> Venue:
        """Build a Venue from location text and optional track name."""
        parts = [p.strip() for p in location_text.split(",")]
        city = parts[0] if len(parts) >= 1 else None
        region = parts[1] if len(parts) >= 2 else None
        country = "United States"

        timezone, inferred = infer_timezone_from_location(
            country=country, city=city
        )
        if not timezone:
            timezone = "America/New_York"
            inferred = True

        return Venue(
            circuit=circuit_name,
            city=city,
            region=region,
            country=country,
            timezone=timezone,
            inferred_timezone=inferred,
        )

    def _generate_event_id(self, name: str, season: int) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        return f"indycar_{season}_{slug}"
