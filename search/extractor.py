"""
Page Extractor — fetch and parse selected URLs into draft events/sessions.

Rules:
  - Never silently invent data.
  - Missing times → status="TBD" + warning
  - No timezone stated → infer from venue + warning
  - Every extracted field records source_url and retrieved_at
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

import httpx
from selectolax.parser import HTMLParser

from models.schema import Event, Session, Venue, Source
from models.enums import SessionType, SessionStatus
from validators.timezone_utils import infer_timezone_from_location
from .domain_trust import DomainTier


@dataclass
class ExtractionWarning:
    """Warning produced during extraction."""

    field: str
    message: str
    source_url: str
    severity: str = "info"  # info | warning | error


@dataclass
class DraftEvent:
    """
    Partially-extracted event — may have missing fields.
    This is the output of the extractor, not yet validated.
    """

    name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    venue_name: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    sessions: List[DraftSession] = field(default_factory=list)
    source_url: str = ""
    source_tier: str = ""
    retrieved_at: Optional[datetime] = None
    confidence: float = 1.0  # 0.0–1.0


@dataclass
class DraftSession:
    """Partially-extracted session."""

    name: str
    session_type: SessionType = SessionType.OTHER
    date: Optional[date] = None
    start_time: Optional[str] = None  # "HH:MM" local
    end_time: Optional[str] = None
    timezone_abbrev: Optional[str] = None
    status: SessionStatus = SessionStatus.TBD
    source_url: str = ""
    confidence: float = 1.0


class PageExtractor:
    """
    Fetch URLs and extract event/session data from HTML pages.

    Constraints:
      - Rate limited (1 req/sec default)
      - Cached by URL
      - Shallow only — no spidering
    """

    def __init__(self, rate_limit: float = 1.0, cache_ttl: float = 3600):
        self._rate_limit = rate_limit
        self._last_request: float = 0
        self._cache: Dict[str, str] = {}
        self._cache_ts: Dict[str, float] = {}
        self._cache_ttl = cache_ttl

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def fetch_page(self, url: str) -> str:
        """Fetch a single page with caching and rate limiting."""
        if url in self._cache:
            ts = self._cache_ts.get(url, 0)
            if time.time() - ts < self._cache_ttl:
                return self._cache[url]

        elapsed = time.time() - self._last_request
        if elapsed < self._rate_limit:
            time.sleep(self._rate_limit - elapsed)
        self._last_request = time.time()

        headers = {
            "User-Agent": "RaceBotDataCollector/1.0 (Educational/Personal Use)"
        }
        with httpx.Client(follow_redirects=True, timeout=30) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text

        self._cache[url] = html
        self._cache_ts[url] = time.time()
        return html

    # ------------------------------------------------------------------
    # Generic extraction
    # ------------------------------------------------------------------

    def extract_schedule_page(
        self,
        url: str,
        series_name: str,
        season: int,
        tier: DomainTier = DomainTier.UNKNOWN,
    ) -> Tuple[List[DraftEvent], List[ExtractionWarning]]:
        """
        Extract events from a schedule/calendar page.

        This is generic — attempts to find tables, lists, or structured
        data with event names, dates, and venues.
        """
        html = self.fetch_page(url)
        tree = HTMLParser(html)
        now = datetime.utcnow()

        events: List[DraftEvent] = []
        warnings: List[ExtractionWarning] = []
        confidence = 1.0 if tier == DomainTier.TIER1 else 0.7 if tier == DomainTier.TIER2 else 0.4

        # Strategy 1: Look for <table> rows with date patterns
        tables = tree.css("table")
        for table in tables:
            rows = table.css("tr")
            for row in rows:
                cells = row.css("td, th")
                if len(cells) < 2:
                    continue

                cell_texts = [c.text(strip=True) for c in cells]
                event = self._try_parse_table_row(
                    cell_texts, season, url, tier, confidence, now
                )
                if event:
                    events.append(event)

        # Strategy 2: Look for structured cards/divs with event names + dates
        if not events:
            events, card_warnings = self._extract_from_cards(
                tree, season, url, tier, confidence, now
            )
            warnings.extend(card_warnings)

        # Strategy 3: Look for <h2>/<h3> headers followed by date text
        if not events:
            events, header_warnings = self._extract_from_headers(
                tree, season, url, tier, confidence, now
            )
            warnings.extend(header_warnings)

        if not events:
            warnings.append(
                ExtractionWarning(
                    field="events",
                    message=f"Could not extract events from {url}",
                    source_url=url,
                    severity="warning",
                )
            )

        return events, warnings

    def extract_event_page(
        self,
        url: str,
        event_name: str,
        season: int,
        tier: DomainTier = DomainTier.UNKNOWN,
    ) -> Tuple[List[DraftSession], List[ExtractionWarning]]:
        """
        Extract sessions from an event detail page.

        Looks for schedule tables, timetables, or lists with session
        names and times.
        """
        html = self.fetch_page(url)
        tree = HTMLParser(html)
        now = datetime.utcnow()

        sessions: List[DraftSession] = []
        warnings: List[ExtractionWarning] = []
        confidence = 1.0 if tier == DomainTier.TIER1 else 0.7 if tier == DomainTier.TIER2 else 0.4

        # Strategy 1: .schedule-table style (IndyCar-like)
        schedule_table = tree.css_first(
            ".schedule-table, .timetable, .event-schedule, "
            "[class*=schedule], [class*=timetable]"
        )
        if schedule_table:
            sessions, s_warnings = self._extract_schedule_table(
                schedule_table, season, url, tier, confidence, now
            )
            warnings.extend(s_warnings)
            if sessions:
                return sessions, warnings

        # Strategy 2: Rows in a table
        for table in tree.css("table"):
            rows = table.css("tr")
            for row in rows:
                cells = row.css("td, th")
                cell_texts = [c.text(strip=True) for c in cells]
                session = self._try_parse_session_row(
                    cell_texts, season, url, tier, confidence, now
                )
                if session:
                    sessions.append(session)

        # Strategy 3: Try any div structure with time-like patterns
        if not sessions:
            sessions, div_warnings = self._extract_sessions_from_divs(
                tree, season, url, tier, confidence, now
            )
            warnings.extend(div_warnings)

        if not sessions:
            warnings.append(
                ExtractionWarning(
                    field="sessions",
                    message=f"No sessions extracted from {url} — times TBC",
                    source_url=url,
                    severity="warning",
                )
            )

        return sessions, warnings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_parse_table_row(
        self,
        cells: List[str],
        season: int,
        url: str,
        tier: DomainTier,
        confidence: float,
        now: datetime,
    ) -> Optional[DraftEvent]:
        """Try to parse a table row as an event (name + date)."""
        # Look for a cell with a date pattern
        date_cell = None
        name_cell = None

        for cell in cells:
            if re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d", cell):
                date_cell = cell
            elif len(cell) > 5 and not re.match(r"^\d", cell):
                if not name_cell:
                    name_cell = cell

        if not name_cell:
            return None

        start, end = self._parse_date_range(date_cell or "", season)

        return DraftEvent(
            name=name_cell.strip(),
            start_date=start,
            end_date=end or start,
            source_url=url,
            source_tier=tier.value,
            retrieved_at=now,
            confidence=confidence,
        )

    def _extract_from_cards(
        self, tree, season, url, tier, confidence, now
    ) -> Tuple[List[DraftEvent], List[ExtractionWarning]]:
        """Try extracting events from card-style divs."""
        events = []
        warnings = []

        # Common card patterns
        selectors = [
            "[class*=event-card]",
            "[class*=race-card]",
            "[class*=schedule-item]",
            ".event-item",
            ".race-item",
        ]

        for selector in selectors:
            cards = tree.css(selector)
            if not cards:
                continue

            for card in cards:
                h = card.css_first("h2, h3, h4, .event-name, .race-name, a")
                if not h:
                    continue

                name = h.text(strip=True)
                if not name or len(name) < 3:
                    continue

                date_text = card.text(strip=True)
                start, end = self._parse_date_range(date_text, season)

                events.append(
                    DraftEvent(
                        name=name,
                        start_date=start,
                        end_date=end or start,
                        source_url=url,
                        source_tier=tier.value,
                        retrieved_at=now,
                        confidence=confidence,
                    )
                )

            if events:
                break

        return events, warnings

    def _extract_from_headers(
        self, tree, season, url, tier, confidence, now
    ) -> Tuple[List[DraftEvent], List[ExtractionWarning]]:
        """Try extracting events from h2/h3 headers."""
        events = []
        warnings = []

        for header in tree.css("h2, h3"):
            text = header.text(strip=True)
            if len(text) < 5 or len(text) > 150:
                continue

            # Look for date in sibling text
            parent = header.parent
            if parent:
                parent_text = parent.text(strip=True)
                start, end = self._parse_date_range(parent_text, season)
                if start:
                    events.append(
                        DraftEvent(
                            name=text,
                            start_date=start,
                            end_date=end or start,
                            source_url=url,
                            source_tier=tier.value,
                            retrieved_at=now,
                            confidence=confidence,
                        )
                    )

        return events, warnings

    def _extract_schedule_table(
        self, table_node, season, url, tier, confidence, now
    ) -> Tuple[List[DraftSession], List[ExtractionWarning]]:
        """Extract sessions from a schedule-table-like structure."""
        sessions = []
        warnings = []
        current_date: Optional[date] = None

        for child in table_node.iter():
            # Day headers
            if child.tag in ("h2", "h3", "h4"):
                day_text = child.text(strip=True)
                current_date = self._parse_single_date(day_text, season)
                continue

            # Session entries — look for time + description
            text = child.text(strip=True)
            if not text or len(text) < 3:
                continue

            # Skip the day header text we already processed
            if child.tag in ("h2", "h3", "h4"):
                continue

            time_match = re.search(
                r"(\d{1,2}:\d{2})\s*(AM|PM|am|pm)?\s*(ET|CT|MT|PT|EST|CST|MST|PST|EDT|CDT|MDT|PDT|CET|CEST|BST|AEST)?",
                text,
            )

            if time_match:
                time_str = time_match.group(0)
                # Get the description — either from a child element or remaining text
                desc = text.replace(time_str, "").strip()
                desc = re.sub(r"^[\s\-–|:]+", "", desc).strip()

                if not desc or len(desc) < 2:
                    # Try getting desc from child elements
                    desc_node = child.css_first(
                        ".schedule-description, .event-name, .session-name"
                    )
                    if desc_node:
                        desc = desc_node.text(strip=True)

                if desc and len(desc) >= 2:
                    session = DraftSession(
                        name=desc,
                        session_type=self._classify_session(desc),
                        date=current_date,
                        start_time=time_match.group(1)
                        + (" " + time_match.group(2) if time_match.group(2) else ""),
                        timezone_abbrev=time_match.group(3),
                        status=SessionStatus.SCHEDULED,
                        source_url=url,
                        confidence=confidence,
                    )
                    sessions.append(session)

        return sessions, warnings

    def _extract_sessions_from_divs(
        self, tree, season, url, tier, confidence, now
    ) -> Tuple[List[DraftSession], List[ExtractionWarning]]:
        """Fallback: look for time patterns anywhere in the page."""
        sessions = []
        warnings = []

        # Find all elements with time-like text
        for node in tree.css("div, li, td, p, span"):
            text = node.text(strip=True)
            if not text or len(text) < 5 or len(text) > 300:
                continue

            time_match = re.search(
                r"(\d{1,2}:\d{2})\s*(AM|PM|am|pm)",
                text,
            )
            if not time_match:
                continue

            # Get what's after the time as session name
            desc = text.replace(time_match.group(0), "").strip()
            desc = re.sub(r"^[\s\-–|:]+", "", desc).strip()

            if desc and len(desc) >= 3 and len(desc) < 100:
                session_type = self._classify_session(desc)
                sessions.append(
                    DraftSession(
                        name=desc,
                        session_type=session_type,
                        start_time=time_match.group(0),
                        status=SessionStatus.SCHEDULED,
                        source_url=url,
                        confidence=confidence,
                    )
                )

        return sessions, warnings

    def _try_parse_session_row(
        self, cells, season, url, tier, confidence, now
    ) -> Optional[DraftSession]:
        """Try to parse a table row as a session."""
        if len(cells) < 2:
            return None

        name = None
        time_str = None
        tz_abbrev = None

        for cell in cells:
            # Time pattern
            tm = re.search(
                r"(\d{1,2}:\d{2})\s*(AM|PM|am|pm)?\s*(ET|CT|MT|PT|CET|BST)?",
                cell,
            )
            if tm and not time_str:
                time_str = tm.group(1)
                if tm.group(2):
                    time_str += " " + tm.group(2)
                tz_abbrev = tm.group(3)
                continue

            # Session name (non-empty, non-numeric)
            if cell and len(cell) > 2 and not re.match(r"^\d+$", cell) and not name:
                name = cell

        if not name:
            return None

        return DraftSession(
            name=name,
            session_type=self._classify_session(name),
            start_time=time_str,
            timezone_abbrev=tz_abbrev,
            status=SessionStatus.SCHEDULED if time_str else SessionStatus.TBD,
            source_url=url,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    DATE_PATTERN = re.compile(
        r"([A-Z][a-z]+)\s+(\d{1,2})\s*[-–]\s*(?:([A-Z][a-z]+)\s+)?(\d{1,2})"
    )

    def _parse_date_range(
        self, text: str, season: int
    ) -> Tuple[Optional[date], Optional[date]]:
        """Parse 'March 6 - 7' or 'Feb 27 - March 1' from text."""
        m = self.DATE_PATTERN.search(text)
        if not m:
            return None, None

        try:
            start_month = m.group(1)
            start_day = int(m.group(2))
            end_month = m.group(3) or start_month
            end_day = int(m.group(4))

            start = datetime.strptime(
                f"{start_month} {start_day} {season}", "%B %d %Y"
            ).date()
            end = datetime.strptime(
                f"{end_month} {end_day} {season}", "%B %d %Y"
            ).date()
            return start, end
        except ValueError:
            return None, None

    def _parse_single_date(self, text: str, season: int) -> Optional[date]:
        """Parse 'Friday, March 6' or 'Mar 6'."""
        m = re.search(r"([A-Z][a-z]+)\s+(\d{1,2})", text)
        if not m:
            return None
        try:
            return datetime.strptime(
                f"{m.group(1)} {m.group(2)} {season}", "%B %d %Y"
            ).date()
        except ValueError:
            try:
                return datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {season}", "%b %d %Y"
                ).date()
            except ValueError:
                return None

    @staticmethod
    def _classify_session(name: str) -> SessionType:
        """Classify session type from name."""
        lower = name.lower()
        if "practice" in lower or "fp" in lower:
            return SessionType.PRACTICE
        elif "qual" in lower or "hyperpole" in lower:
            return SessionType.QUALIFYING
        elif "race" in lower and "feature" not in lower:
            return SessionType.RACE
        elif "sprint" in lower:
            return SessionType.SPRINT
        elif "warmup" in lower or "warm up" in lower or "warm-up" in lower:
            return SessionType.WARMUP
        elif "test" in lower or "shakedown" in lower:
            return SessionType.TEST
        elif "stage" in lower or "ss" in lower:
            return SessionType.RALLY_STAGE
        else:
            return SessionType.OTHER
