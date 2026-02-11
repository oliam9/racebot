"""
Moto3 Connector using official PulseLive API.
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

class Moto3Connector(Connector):
    """
    Connector for Moto3 using the official API (api.pulselive.motogp.com).
    Bypasses the need for scraping/rendering JavaScript.
    """
    
    API_BASE = "https://api.pulselive.motogp.com/motogp/v1"
    
    def __init__(self):
        super().__init__()
        self._moto3_category_id = None  # Cache Moto3 category ID
        
    @property
    def id(self) -> str:
        return "moto3_official"

    @property
    def name(self) -> str:
        return "Moto3 Official API"
        
    def supported_series(self) -> List[SeriesDescriptor]:
        """Return list of supported series."""
        return [
            SeriesDescriptor(
                series_id="moto3",
                name="Moto3",
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
                    
            logger.warning(f"Moto3 season {year} not found in API")
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch Moto3 seasons: {e}")
            return None
    
    def _get_moto3_category_id(self, season_uuid: str) -> Optional[str]:
        """Fetch the Moto3 category UUID (cached)."""
        if self._moto3_category_id:
            return self._moto3_category_id
            
        try:
            url = f"{self.API_BASE}/results/categories"
            params = {"seasonUuid": season_uuid}
            resp = httpx.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            
            categories = resp.json()
            for cat in categories:
                # Moto3 has legacy_id=1 or name contains "Moto3"
                if cat.get("legacy_id") == 1 or "Moto3" in cat.get("name", ""):
                    self._moto3_category_id = cat.get("id")
                    return self._moto3_category_id
            
            logger.warning("Moto3 category not found")
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch Moto3 categories: {e}")
            return None
    
    def _get_event_sessions(self, event_id: str, category_id: str) -> List[Dict[str, Any]]:
        """Fetch sessions for a specific event."""
        try:
            url = f"{self.API_BASE}/results/sessions"
            params = {
                "eventUuid": event_id,
                "categoryUuid": category_id
            }
            resp = httpx.get(url, params=params, timeout=10.0)
            resp.raise_for_status()
            
            return resp.json()
            
        except Exception as e:
            logger.warning(f"Failed to fetch sessions for event {event_id}: {e}")
            return []

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        """Fetch full season data from API."""
        if series_id != "moto3":
            raise ValueError(f"Moto3 connector does not support series: {series_id}")
            
        season_uuid = self._get_season_id(season)
        if not season_uuid:
            raise ValueError(f"Could not find season ID for {season}")
            
        # Fetch events
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
                content=resp.text,
                retrieved_at=datetime.utcnow(),
                url=str(resp.url),
                content_type="application/json",
                metadata={
                    "series_id": series_id, 
                    "season": season,
                    "season_uuid": season_uuid
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch Moto3 calendar: {e}")
            raise

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        """Parse API JSON response into Events."""
        import json
        
        try:
            data = json.loads(raw.content)
        except json.JSONDecodeError:
            logger.error("Failed to parse Moto3 API response")
            return []
            
        events = []
        for item in data:
            if item.get("test") == True:
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
            
        start_str = data.get("date_start") 
        end_str = data.get("date_end")
        
        if not start_str or not end_str:
            return None
            
        start_date = parser.isoparse(start_str).date()
        end_date = parser.isoparse(end_str).date()
        
        circuit_info = data.get("circuit", {})
        country_info = data.get("country", {})
        
        circuit_name = circuit_info.get("name") if circuit_info else "TBD"
        city = circuit_info.get("place") if circuit_info else None
        country_code = circuit_info.get("nation") if circuit_info else country_info.get("iso", "Unknown")
        
        from validators.timezone_utils import infer_timezone_from_location
        tz_name, _ = infer_timezone_from_location(city=city, country=country_code) if city else (None, False)
        if not tz_name:
            tz_name = "UTC"
        
        sessions = []
        event_id = data.get("id")
        season_uuid = raw.metadata.get("season_uuid")
        
        if event_id and season_uuid:
            category_id = self._get_moto3_category_id(season_uuid)
            if category_id:
                session_data = self._get_event_sessions(event_id, category_id)
                for sess in session_data:
                    session = self._parse_session(sess)
                    if session:
                        sessions.append(session)
        
        source = Source(
            url=raw.url,
            provider_name="Moto3 Official API",
            retrieved_at=raw.retrieved_at,
            extraction_method="api",
            discovered_endpoints=[raw.url]
        )
        
        return Event(
            event_id=data.get("id"),
            series_id=raw.metadata.get("series_id", "moto3"),
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

    def _parse_session(self, data: Dict[str, Any]) -> Optional[Session]:
        """Parse session object from API response."""
        session_type_str = data.get("type", "")
        number = data.get("number", 1)
        
        if session_type_str == "RAC":
            stype = SessionType.RACE
            name = "Race"
        elif session_type_str == "Q":
            stype = SessionType.QUALIFYING
            name = f"Qualifying {number}" if number else "Qualifying"
        elif session_type_str == "FP":
            stype = SessionType.PRACTICE
            name = f"Free Practice {number}"
        elif session_type_str == "PR":
            stype = SessionType.PRACTICE
            name = f"Practice {number}" if number else "Practice"
        elif session_type_str == "WUP":
            stype = SessionType.WARMUP
            name = "Warm Up"
        else:
            stype = SessionType.PRACTICE
            name = f"{session_type_str} {number}" if number else session_type_str
        
        start = data.get("date")
        if not start:
            return None
            
        sid = data.get("id")
        status_str = data.get("status", "SCHEDULED")
        if status_str == "FINISHED":
            status = SessionStatus.SCHEDULED
        elif status_str == "CANCELLED":
            status = SessionStatus.CANCELLED
        else:
            status = SessionStatus.SCHEDULED
        
        return Session(
            session_id=sid,
            type=stype,
            name=name,
            start=start,
            end=None,
            status=status
        )
