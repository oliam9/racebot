"""
MotoGP Connector using official PulseLive API.
"""
from datetime import datetime
from typing import List, Dict, Any, Optional
import httpx
import pytz
from dateutil import parser
import logging

from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SeriesCategory, SessionType, SessionStatus
from .base import Connector, RawSeriesPayload

logger = logging.getLogger(__name__)

class MotoGPConnector(Connector):
    """
    Connector for MotoGP using the official API (api.pulselive.motogp.com).
    Bypasses the need for scraping/rendering JavaScript.
    """
    
    API_BASE = "https://api.pulselive.motogp.com/motogp/v1"
    
    def __init__(self):
        super().__init__()
        
    @property
    def id(self) -> str:
        return "motogp_official"

    @property
    def name(self) -> str:
        return "MotoGP Official API"
        
    def supported_series(self) -> List[SeriesDescriptor]:
        """Return list of supported series."""
        return [
            SeriesDescriptor(
                series_id="motogp",
                name="MotoGP",
                category=SeriesCategory.MOTORCYCLE,
                connector_id=self.id
            )
        ]
        
    def _get_season_id(self, year: int) -> Optional[str]:
        """Fetch the season UUID for a given year."""
        try:
            url = f"{self.API_BASE}/results/seasons"
            resp = httpx.get(url, timeout=10.0)
            resp.raise_for_status()
            
            seasons = resp.json()
            for s in seasons:
                if s.get("year") == year:
                    return s.get("id")
                    
            logger.warning(f"MotoGP season {year} not found in API")
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch MotoGP seasons: {e}")
            return None

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        """Fetch full season data from API."""
        if series_id != "motogp":
            raise ValueError(f"MotoGP connector does not support series: {series_id}")
            
        season_uuid = self._get_season_id(season)
        if not season_uuid:
            raise ValueError(f"Could not find season ID for {season}")
            
        # Fetch events
        # Note: isTest=false filters out official tests, usually users want race weekends
        url = f"{self.API_BASE}/results/events"
        params = {
            "seasonUuid": season_uuid,
            "isTest": "false", 
            "sponsor": "true"
        }
        
        try:
            resp = httpx.get(url, params=params, timeout=15.0)
            resp.raise_for_status()
            
            return RawSeriesPayload(
                content=resp.text,  # Store JSON as text
                retrieved_at=datetime.utcnow(),
                url=str(resp.url),
                content_type="application/json",
                metadata={"series_id": series_id, "season": season}
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch MotoGP calendar: {e}")
            raise

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        """Parse API JSON response into Events."""
        import json
        
        try:
            data = json.loads(raw.content)
        except json.JSONDecodeError:
            logger.error("Failed to parse MotoGP API response")
            return []
            
        events = []
        for item in data:
            # Filter for GP events only (exclude tests/media if api params didn't catch them)
            # kind can be "GP", "TEST", "MEDIA"
            if item.get("kind") != "GP":
                continue
                
            try:
                event = self._parse_event(item, raw)
                if event:
                    events.append(event)
            except Exception as e:
                logger.warning(f"Failed to parse event {item.get('name')}: {e}")
                
        return events

    def _parse_event(self, data: Dict[str, Any], raw: RawSeriesPayload) -> Optional[Event]:
        """Parse a single event object from API."""
        name = data.get("name") or data.get("sponsored_name")
        if not name:
            return None
            
        # Dates are usually ISO strings
        start_str = data.get("date_start") 
        end_str = data.get("date_end")
        
        if not start_str or not end_str:
            return None
            
        # Parse dates (handle timezones if present, but Event model expects date objects)
        start_date = parser.isoparse(start_str).date()
        end_date = parser.isoparse(end_str).date()
        
        # Venue info
        circuit_info = data.get("circuit", {})
        place_info = data.get("place", {}) or {}
        
        # Sometimes circuit is null but place is present (common for TBD events)
        circuit_name = circuit_info.get("name") if circuit_info else "TBD"
        city = circuit_info.get("place") if circuit_info else place_info.get("city")
        country_code = circuit_info.get("nation") if circuit_info else data.get("country")
        
        # Timezone
        # API provides "time_zone": "EUROPE/MADRID"
        tz_name = data.get("time_zone", "UTC")
        
        # Sessions
        sessions = []
        api_schedule = data.get("broadcasts", []) # Actual sessions seem to be in 'broadcasts' list with type='SESSION'
        
        # Check if broadcasts is the right place, debug output had 'broadcasts' with valid sessions
        # But sometimes schedules are nested differently. data['schedule'] exists too.
        # Based on motogp_api_4.json, 'broadcasts' contains sessions.
        
        for b in api_schedule:
            if b.get("type") == "SESSION" and b.get("kind") in ["PRACTICE", "QUALIFYING", "RACE", "SPRINT"]:
                session = self._parse_session(b, tz_name)
                if session:
                    sessions.append(session)
        
        # Construct Source
        source = Source(
            url=raw.url,
            provider_name="MotoGP Official API",
            retrieved_at=raw.retrieved_at,
            extraction_method="api",
            discovered_endpoints=[raw.url]
        )
        
        return Event(
            event_id=data.get("id"),
            series_id=raw.series_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            venue=Venue(
                circuit=circuit_name,
                city=city,
                country=country_code or "Unknown",
                timezone=tz_name
            ),
            sessions=sessions,
            sources=[source]
        )

    def _parse_session(self, data: Dict[str, Any], tz_name: str) -> Optional[Session]:
        """Parse session object."""
        name = data.get("name", "Unknown Session")
        short_name = data.get("shortname", "")
        kind = data.get("kind", "")
        
        # Refine name if needed
        # Example: shortname="RACE", name="Race" -> OK
        # Example: shortname="Q2", name="Qualifying 2" -> OK
        
        # Map to SessionType
        stype = SessionType.PRACTICE
        if kind == "RACE":
            stype = SessionType.RACE
        elif kind == "QUALIFYING":
            stype = SessionType.QUALIFYING
        elif kind == "SPRINT":
            stype = SessionType.RACE # Or separate type if supported? Schema has RACE.
            name = f"Sprint Rate - {name}"
            
        # Dates
        start = data.get("date_start")
        end = data.get("date_end")
        
        if not start:
            return None
            
        # ID
        sid = data.get("id")
        
        return Session(
            session_id=sid,
            type=stype,
            name=name,
            start=start, # API returns ISO format which aligns with schema
            end=end,
            status=SessionStatus.SCHEDULED # Assume scheduled for now
        )
