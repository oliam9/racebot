"""
Formula 1 connector — uses OpenF1 API for comprehensive F1 data.
OpenF1 provides real-time and historical F1 data including race schedules,
sessions, and detailed event information.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date
import logging
from dateutil import parser
from .base import Connector, RawSeriesPayload
from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SessionType, SessionStatus, SeriesCategory
from validators.timezone_utils import infer_timezone_from_location

logger = logging.getLogger(__name__)


class F1Connector(Connector):
    """Connector for Formula 1 using OpenF1 API."""

    # OpenF1 API - modern, actively maintained F1 data API
    API_BASE = "https://api.openf1.org/v1"

    @property
    def id(self) -> str:
        return "f1_openf1"

    @property
    def name(self) -> str:
        return "Formula 1 (OpenF1 API)"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="f1",
                name="Formula 1",
                category=SeriesCategory.OPENWHEEL,
                connector_id=self.id,
            )
        ]

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        """Fetch F1 season schedule from OpenF1 API."""
        if series_id != "f1":
            raise ValueError(f"Unsupported series: {series_id}")

        cached = self._get_from_cache(series_id, season)
        if cached:
            return cached

        # Get meetings (race weekends) for the season
        meetings_url = f"{self.API_BASE}/meetings?year={season}"
        
        try:
            response = self._http_get(meetings_url, timeout=10)
            
            payload = RawSeriesPayload(
                content=response.text,
                content_type="application/json",
                url=meetings_url,
                retrieved_at=datetime.utcnow(),
                metadata={"series_id": series_id, "season": season},
            )

            self._save_to_cache(series_id, season, payload)
            return payload
            
        except Exception as e:
            logger.error(f"Failed to fetch F1 {season} season: {e}")
            raise

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        """Parse OpenF1 API JSON response into Events."""
        import json
        
        try:
            meetings = json.loads(raw.content)
        except json.JSONDecodeError:
            logger.error("Failed to parse F1 API response")
            return []
        
        if not meetings:
            logger.warning(f"No meetings found for F1 season {raw.metadata.get('season')}")
            return []
        
        events = []
        for meeting_data in meetings:
            # Skip pre-season testing
            meeting_name = meeting_data.get("meeting_name", "")
            if "testing" in meeting_name.lower() or "test" in meeting_name.lower():
                continue
            
            try:
                event = self._parse_event(meeting_data, raw)
                if event:
                    events.append(event)
            except Exception as e:
                logger.warning(f"Failed to parse F1 meeting {meeting_name}: {e}")
        
        return events

    def _parse_event(self, data: Dict[str, Any], raw: RawSeriesPayload) -> Optional[Event]:
        """Parse a single meeting (race weekend) from OpenF1 API."""
        
        # Event name
        race_name = data.get("meeting_name")
        if not race_name:
            return None
        
        meeting_key = data.get("meeting_key")
        year = data.get("year")
        
        # Parse dates
        date_start_str = data.get("date_start")
        date_end_str = data.get("date_end")
        
        if not date_start_str or not date_end_str:
            return None
        
        start_date = parser.isoparse(date_start_str).date()
        end_date = parser.isoparse(date_end_str).date()
        
        # Location and circuit info
        circuit_short = data.get("circuit_short_name", "TBD")
        location = data.get("location")
        country_name = data.get("country_name", "Unknown")
        country_code = data.get("country_code")
        
        # Get full circuit name from circuit mapping
        circuit_name = self._get_circuit_name(circuit_short, location)
        
        # GMT offset to timezone conversion
        gmt_offset = data.get("gmt_offset", "00:00:00")
        timezone = self._gmt_offset_to_timezone(gmt_offset, country_code, location)
        
        # Fetch sessions for this meeting
        sessions = self._fetch_sessions(meeting_key, raw)
        
        # Construct Source
        source = Source(
            url=raw.url,
            provider_name="OpenF1 API",
            retrieved_at=raw.retrieved_at,
            extraction_method="api",
            discovered_endpoints=[raw.url, f"{self.API_BASE}/sessions"]
        )
        
        # Generate event ID
        event_id = f"f1_{year}_{meeting_key}"
        
        return Event(
            event_id=event_id,
            series_id="f1",
            name=race_name,
            start_date=start_date,
            end_date=end_date,
            venue=Venue(
                circuit=circuit_name,
                city=location,
                country=country_name,
                timezone=timezone,
                inferred_timezone=False
            ),
            sessions=sessions,
            sources=[source]
        )

    def _fetch_sessions(self, meeting_key: int, raw: RawSeriesPayload) -> List[Session]:
        """Fetch sessions for a specific meeting."""
        import json
        
        sessions_url = f"{self.API_BASE}/sessions?meeting_key={meeting_key}"
        
        try:
            response = self._http_get(sessions_url, timeout=10)
            sessions_data = json.loads(response.text)
            
            sessions = []
            for session_data in sessions_data:
                session = self._parse_session(session_data, meeting_key)
                if session:
                    sessions.append(session)
            
            return sessions
            
        except Exception as e:
            logger.warning(f"Failed to fetch sessions for meeting {meeting_key}: {e}")
            return []

    def _parse_session(self, data: Dict[str, Any], meeting_key: int) -> Optional[Session]:
        """Parse a single session from OpenF1 API."""
        
        session_name = data.get("session_name")
        session_type_str = data.get("session_type", "").lower()
        session_key = data.get("session_key")
        
        if not session_name:
            return None
        
        # Map OpenF1 session types to our SessionType enum
        if "race" in session_type_str:
            stype = SessionType.RACE
        elif "qualifying" in session_type_str or "quali" in session_type_str:
            stype = SessionType.QUALIFYING
        elif "sprint" in session_type_str:
            stype = SessionType.RACE  # Sprint is a race type
            if "Sprint" not in session_name:
                session_name = f"Sprint {session_name}"
        elif "practice" in session_type_str:
            stype = SessionType.PRACTICE
        else:
            stype = SessionType.OTHER
        
        # Start time
        start = data.get("date_start")
        end = data.get("date_end")
        
        return Session(
            session_id=f"f1_session_{session_key}",
            type=stype,
            name=session_name,
            start=start,
            end=end or "TBC",
            status=SessionStatus.SCHEDULED
        )

    def _get_circuit_name(self, circuit_short: str, location: str) -> str:
        """Map circuit short name to full circuit name."""
        circuit_map = {
            "Sakhir": "Bahrain International Circuit",
            "Melbourne": "Albert Park Circuit",
            "Shanghai": "Shanghai International Circuit",
            "Suzuka": "Suzuka International Racing Course",
            "Miami": "Miami International Autodrome",
            "Imola": "Autodromo Enzo e Dino Ferrari",
            "Monaco": "Circuit de Monaco",
            "Montreal": "Circuit Gilles Villeneuve",
            "Barcelona": "Circuit de Barcelona-Catalunya",
            "Red Bull Ring": "Red Bull Ring",
            "Silverstone": "Silverstone Circuit",
            "Hungaroring": "Hungaroring",
            "Spa-Francorchamps": "Circuit de Spa-Francorchamps",
            "Zandvoort": "Circuit Zandvoort",
            "Monza": "Autodromo Nazionale di Monza",
            "Baku": "Baku City Circuit",
            "Marina Bay": "Marina Bay Street Circuit",
            "Austin": "Circuit of the Americas",
            "Mexico City": "Autódromo Hermanos Rodríguez",
            "São Paulo": "Autódromo José Carlos Pace",
            "Las Vegas": "Las Vegas Street Circuit",
            "Lusail": "Lusail International Circuit",
            "Yas Marina": "Yas Marina Circuit",
            "Jeddah": "Jeddah Corniche Circuit",
        }
        
        return circuit_map.get(circuit_short, circuit_short or location or "TBD")

    def _gmt_offset_to_timezone(self, gmt_offset: str, country_code: str, location: str) -> str:
        """Convert GMT offset to IANA timezone using location."""
        # Use timezone inference which is more accurate
        tz_name, _ = infer_timezone_from_location(city=location, country=country_code)
        
        if tz_name:
            return tz_name
        
        # Fallback: Manual mapping for common F1 locations
        # Using tuple of (country_code, location_name) for exact matching
        location_key = (country_code, location)
        
        location_tz_map = {
            # Current 2026 locations
            ("AUS", "Melbourne"): "Australia/Melbourne",
            ("CHN", "Shanghai"): "Asia/Shanghai",
            ("JPN", "Suzuka"): "Asia/Tokyo",
            ("BHR", "Sakhir"): "Asia/Bahrain",
            ("KSA", "Jeddah"): "Asia/Riyadh",
            ("ARE", "Yas Marina"): "Asia/Dubai",
            ("UAE", "Yas Marina"): "Asia/Dubai",
            ("ITA", "Monza"): "Europe/Rome",
            ("ITA", "Imola"): "Europe/Rome",
            ("MON", "Monte Carlo"): "Europe/Monaco",
            ("MCO", "Monaco"): "Europe/Monaco",
            ("GBR", "Silverstone"): "Europe/London",
            ("BEL", "Spa-Francorchamps"): "Europe/Brussels",
            ("NLD", "Zandvoort"): "Europe/Amsterdam",
            ("NED", "Zandvoort"): "Europe/Amsterdam",
            ("HUN", "Hungaroring"): "Europe/Budapest",
            ("AUT", "Spielberg"): "Europe/Vienna",
            ("ESP", "Barcelona"): "Europe/Madrid",
            ("ESP", "Madrid"): "Europe/Madrid",
            ("CAN", "Montreal"): "America/Toronto",
            ("CAN", "Montréal"): "America/Toronto",
            ("USA", "Austin"): "America/Chicago",
            ("USA", "Miami"): "America/New_York",
            ("USA", "Miami Gardens"): "America/New_York",
            ("USA", "Las Vegas"): "America/Los_Angeles",
            ("MEX", "Mexico City"): "America/Mexico_City",
            ("BRA", "São Paulo"): "America/Sao_Paulo",
            ("SGP", "Singapore"): "Asia/Singapore",
            ("SGP", "Marina Bay"): "Asia/Singapore",
            ("QAT", "Lusail"): "Asia/Qatar",
            ("QAT", "Doha"): "Asia/Qatar",
            ("AZE", "Baku"): "Asia/Baku",
        }
        
        tz = location_tz_map.get(location_key)
        if tz:
            return tz
        
        # Last resort: UTC
        logger.debug(f"Could not determine timezone for {location}, {country_code}. Using UTC.")
        return "UTC"
