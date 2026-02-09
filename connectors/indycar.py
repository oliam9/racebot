"""
IndyCar connector using official calendar ICS feed.
"""

from typing import List
from datetime import datetime, date
from icalendar import Calendar
import re
from .base import Connector, RawSeriesPayload
from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SessionType, SessionStatus, SeriesCategory
from validators.timezone_utils import infer_timezone_from_location


class IndyCarConnector(Connector):
    """Connector for IndyCar series using official ICS calendar feed."""
    
    # ICS feed URL (webcal:// can be replaced with https://)
    ICS_FEED_URL = "https://sync.roktcalendar.com/webcal/3aef020f-0a9a-4c45-8219-9610e2269f59"
    
    @property
    def id(self) -> str:
        return "indycar_official"
    
    @property
    def name(self) -> str:
        return "IndyCar Official Calendar"
    
    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="indycar",
                name="NTT IndyCar Series",
                category=SeriesCategory.OPENWHEEL,
                connector_id=self.id
            )
        ]
    
    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        """
        Fetch IndyCar calendar for a season.
        
        Note: The ICS feed contains all events, we'll filter by season during extraction.
        """
        if series_id != "indycar":
            raise ValueError(f"Unsupported series: {series_id}")
        
        # Check cache first
        cached = self._get_from_cache(series_id, season)
        if cached:
            return cached
        
        # Fetch ICS feed
        response = self._http_get(self.ICS_FEED_URL)
        
        payload = RawSeriesPayload(
            content=response.text,
            content_type="text/calendar",
            url=self.ICS_FEED_URL,
            retrieved_at=datetime.utcnow(),
            metadata={"season": season}
        )
        
        # Cache it
        self._save_to_cache(series_id, season, payload)
        
        return payload
    
    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        """
        Extract events from ICS calendar.
        
        The ICS feed contains individual sessions as calendar events.
        We need to group them by race weekend into Event objects.
        """
        # Parse ICS calendar
        cal = Calendar.from_ical(raw.content)
        
        # Extract season from metadata
        season = raw.metadata.get("season")
        
        # Group calendar events by event/weekend
        # Strategy: Look for events in same weekend (same week + location)
        ical_events = []
        for component in cal.walk():
            if component.name == "VEVENT":
                ical_events.append(component)
        
        # Filter by season
        if season:
            ical_events = [
                evt for evt in ical_events
                if evt.get('DTSTART').dt.year == season
            ]
        
        # Group by event (heuristic: events within 7 days and similar location/name)
        events = self._group_into_events(ical_events, season or 2024, raw)
        
        return events
    
    def _group_into_events(
        self,
        ical_events: List,
        season: int,
        raw: RawSeriesPayload
    ) -> List[Event]:
        """
        Group ICS calendar events into motorsport Event objects.
        
        ICS events are individual sessions, we group them by weekend/location.
        """
        # Sort by start time (normalize for comparison)
        def get_sort_key(e):
            dt = e.get('DTSTART').dt
            # Convert date to datetime
            if isinstance(dt, date) and not isinstance(dt, datetime):
                dt = datetime.combine(dt, datetime.min.time())
            # Strip timezone info if present to allow comparison with naive datetimes/dates
            if isinstance(dt, datetime) and dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        
        ical_events.sort(key=get_sort_key)
        
        events: List[Event] = []
        current_event_sessions = []
        current_event_name = None
        current_event_start = None
        current_event_end = None
        current_location = None
        
        for ical_evt in ical_events:
            summary = str(ical_evt.get('SUMMARY', ''))
            start_dt = ical_evt.get('DTSTART').dt
            end_dt = ical_evt.get('DTEND').dt if ical_evt.get('DTEND') else None
            location = str(ical_evt.get('LOCATION', ''))
            
            # Extract event name and session type from summary
            # IndyCar format is typically: "Event Name - Session Type"
            event_name, session_name = self._parse_summary(summary)
            
            # Get just the date part for comparison
            if isinstance(start_dt, datetime):
                start_date = start_dt.date()
            else:
                start_date = start_dt
            
            # Start new event if:
            # 1. First event
            # 2. Different event name
            # 3. More than 7 days since last session
            should_start_new = (
                len(events) == 0 and len(current_event_sessions) == 0
            ) or (
                current_event_name and event_name != current_event_name
            ) or (
                current_event_end and (start_date - current_event_end).days > 7
            )
            
            if should_start_new and current_event_sessions:
                # Finalize current event
                event = self._create_event(
                    current_event_name,
                    current_event_start,
                    current_event_end,
                    current_location,
                    current_event_sessions,
                    season,
                    raw
                )
                events.append(event)
                current_event_sessions = []
            
            # Create session
            session = self._create_session(summary, session_name, start_dt, end_dt)
            current_event_sessions.append(session)
            current_event_name = event_name
            current_location = location
            
            if current_event_start is None or start_date < current_event_start:
                current_event_start = start_date
            
            if end_dt:
                if isinstance(end_dt, datetime):
                    end_date = end_dt.date()
                else:
                    end_date = end_dt
            else:
                end_date = start_date
            
            if current_event_end is None or end_date > current_event_end:
                current_event_end = end_date
        
        # Don't forget last event
        if current_event_sessions:
            event = self._create_event(
                current_event_name,
                current_event_start,
                current_event_end,
                current_location,
                current_event_sessions,
                season,
                raw
            )
            events.append(event)
        
        return events
    
    def _parse_summary(self, summary: str) -> tuple:
        """
        Parse ICS summary into event name and session name.
        
        Typical format: "Indianapolis 500 - Race" or "Grand Prix of St. Petersburg - Practice 1"
        """
        # Try to split on " - "
        if " - " in summary:
            parts = summary.split(" - ", 1)
            return parts[0].strip(), parts[1].strip()
        else:
            # Assume entire summary is event name, session is "Unknown"
            return summary.strip(), "Unknown"
    
    def _create_session(
        self,
        full_name: str,
        session_name: str,
        start_dt,
        end_dt
    ) -> Session:
        """Create a Session object from ICS event."""
        # Classify session type
        session_type = self._classify_session_type(session_name)
        
        # Generate session ID
        session_id = self._generate_session_id(full_name)
        
        # Convert datetime to ISO string
        if isinstance(start_dt, datetime):
            start_iso = start_dt.isoformat()
        else:
            # Date only - set to TBD
            start_iso = None
            session_status = SessionStatus.TBD
        
        if end_dt:
            if isinstance(end_dt, datetime):
                end_iso = end_dt.isoformat()
            else:
                end_iso = None
        else:
            end_iso = None
        
        return Session(
            session_id=session_id,
            type=session_type,
            name=session_name,
            start=start_iso,
            end=end_iso,
            status=SessionStatus.SCHEDULED if start_iso else SessionStatus.TBD
        )
    
    def _classify_session_type(self, session_name: str) -> SessionType:
        """Classify session type from name."""
        lower = session_name.lower()
        
        if "practice" in lower or "fp" in lower:
            return SessionType.PRACTICE
        elif "qual" in lower:
            return SessionType.QUALIFYING
        elif "race" in lower and "feature" not in lower:
            return SessionType.RACE
        elif "warmup" in lower or "warm up" in lower:
            return SessionType.WARMUP
        else:
            return SessionType.OTHER
    
    def _create_event(
        self,
        name: str,
        start_date: date,
        end_date: date,
        location: str,
        sessions: List[Session],
        season: int,
        raw: RawSeriesPayload
    ) -> Event:
        """Create an Event object from grouped sessions."""
        # Generate event ID
        event_id = self._generate_event_id(name, season)
        
        # Parse location into venue
        venue = self._parse_location(location)
        
        # Create source
        source = self.create_source(raw.url, raw.retrieved_at)
        
        return Event(
            event_id=event_id,
            series_id="indycar",
            name=name,
            start_date=start_date,
            end_date=end_date,
            venue=venue,
            sessions=sessions,
            sources=[source],
            last_verified_at=raw.retrieved_at
        )
    
    def _parse_location(self, location: str) -> Venue:
        """
        Parse location string into Venue object.
        
        Location format varies, e.g.: "Indianapolis Motor Speedway, Indianapolis, IN"
        """
        # Simple parsing - split by comma
        parts = [p.strip() for p in location.split(',')]
        
        circuit = None
        city = None
        region = None
        country = "United States"  # IndyCar is primarily US-based
        
        if len(parts) >= 3:
            circuit = parts[0]
            city = parts[1]
            region = parts[2]
        elif len(parts) == 2:
            circuit = parts[0]
            city = parts[1]
        elif len(parts) == 1:
            circuit = parts[0]
        
        # Infer timezone
        timezone, inferred = infer_timezone_from_location(
            country=country,
            city=city
        )
        
        if not timezone:
            # Default to Eastern (most IndyCar races)
            timezone = "America/New_York"
            inferred = True
        
        return Venue(
            circuit=circuit,
            city=city,
            region=region,
            country=country,
            timezone=timezone,
            inferred_timezone=inferred
        )
    
    def _generate_event_id(self, name: str, season: int) -> str:
        """Generate stable event ID from name and season."""
        # Slugify name
        slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        return f"indycar_{season}_{slug}"
    
    def _generate_session_id(self, full_name: str) -> str:
        """Generate stable session ID from full name."""
        slug = re.sub(r'[^a-z0-9]+', '_', full_name.lower()).strip('_')
        return slug
