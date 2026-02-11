"""
FIA World Rallycross Championship Connector.
Scrapes https://www.fiaworldrallycross.com/events for schedule data.
"""
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
import json
import re
import logging
from dateutil import parser as date_parser

from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SeriesCategory, SessionType, SessionStatus
from .base import Connector, RawSeriesPayload
from validators.timezone_utils import infer_timezone_from_location

logger = logging.getLogger(__name__)


class WorldRXConnector(Connector):
    """
    Connector for FIA World Rallycross Championship.
    Uses web scraping with API endpoint detection.
    """
    
    BASE_URL = "https://www.fiaworldrallycross.com"
    EVENTS_URL = "https://www.fiaworldrallycross.com/events"
    
    @property
    def id(self) -> str:
        return "worldrx_official"

    @property
    def name(self) -> str:
        return "FIA World Rallycross Championship"
        
    def supported_series(self) -> List[SeriesDescriptor]:
        """Return list of supported series."""
        return [
            SeriesDescriptor(
                series_id="worldrx",
                name="FIA World Rallycross Championship",
                category=SeriesCategory.RALLY,
                connector_id=self.id
            )
        ]
    
    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        """Fetch World RX season schedule."""
        if series_id != "worldrx":
            raise ValueError(f"World RX connector does not support series: {series_id}")
        
        # Try various API endpoints
        api_endpoints = [
            f"{self.BASE_URL}/api/events?year={season}",
            f"{self.BASE_URL}/api/calendar/{season}",
            f"https://api.fiaworldrallycross.com/v1/events?season={season}",
        ]
        
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                # Try API endpoints first
                for api_url in api_endpoints:
                    try:
                        resp = client.get(api_url)
                        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                            return RawSeriesPayload(
                                content=resp.text,
                                retrieved_at=datetime.utcnow(),
                                url=api_url,
                                content_type="application/json",
                                metadata={"series_id": series_id, "season": season}
                            )
                    except Exception as e:
                        logger.debug(f"API endpoint {api_url} failed: {e}")
                
                # Fall back to HTML scraping
                resp = client.get(self.EVENTS_URL)
                resp.raise_for_status()
                
                return RawSeriesPayload(
                    content=resp.text,
                    retrieved_at=datetime.utcnow(),
                    url=self.EVENTS_URL,
                    content_type="text/html",
                    metadata={"series_id": series_id, "season": season}
                )
                
        except Exception as e:
            logger.error(f"Failed to fetch World RX calendar: {e}")
            raise
    
    def extract(self, payload: RawSeriesPayload) -> List[Event]:
        """Parse World RX season data into Event objects."""
        series_id = payload.metadata.get("series_id", "worldrx")
        season = payload.metadata.get("season", datetime.now().year)
        
        if payload.content_type == "application/json":
            return self._parse_json(payload, series_id, season)
        else:
            return self._parse_html(payload, series_id, season)
    
    def _parse_json(self, payload: RawSeriesPayload, series_id: str, season: int) -> List[Event]:
        """Parse JSON API response."""
        events = []
        
        try:
            data = json.loads(payload.content)
            
            # Handle various JSON structures
            events_list = data
            if isinstance(data, dict):
                events_list = data.get("events", data.get("data", data.get("rounds", [])))
            
            for item in events_list:
                try:
                    event = self._parse_event_json(item, series_id, season, payload.url)
                    if event:
                        events.append(event)
                except Exception as e:
                    logger.warning(f"Failed to parse World RX event: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to parse World RX JSON: {e}")
        
        return events
    
    def _parse_event_json(self, item: Dict[str, Any], series_id: str, season: int, source_url: str) -> Optional[Event]:
        """Parse a single event from JSON."""
        # Extract basic info
        name = item.get("name", item.get("title", item.get("eventName", "Unknown Event")))
        event_id = item.get("id", item.get("eventId", ""))
        
        # Extract dates
        start_date = None
        end_date = None
        
        for date_field in ["startDate", "start_date", "date", "dateFrom"]:
            if date_field in item and item[date_field]:
                try:
                    dt = date_parser.parse(str(item[date_field]))
                    start_date = dt.date()
                    break
                except:
                    pass
        
        for date_field in ["endDate", "end_date", "dateTo"]:
            if date_field in item and item[date_field]:
                try:
                    dt = date_parser.parse(str(item[date_field]))
                    end_date = dt.date()
                    break
                except:
                    pass
        
        if not start_date:
            return None
        
        if not end_date:
            end_date = start_date
        
        # Extract venue info
        location = item.get("location", item.get("venue", item.get("circuit", {})))
        venue_name = location.get("name", "") if isinstance(location, dict) else str(location)
        city = location.get("city", "") if isinstance(location, dict) else ""
        country = location.get("country", "") if isinstance(location, dict) else ""
        
        # Try alternate field names
        if not venue_name:
            venue_name = item.get("circuit", item.get("track", ""))
        if not city:
            city = item.get("city", "")
        if not country:
            country = item.get("country", "")
        
        if not country:
            country = "Unknown"
        
        # Infer timezone
        timezone = infer_timezone_from_location(country, city)
        
        venue = Venue(
            circuit=venue_name or None,
            city=city or None,
            country=country,
            timezone=timezone,
            inferred_timezone=True
        )
        
        # Generate event_id
        round_num = item.get("round", item.get("roundNumber", 0))
        event_id_generated = f"{series_id}_{season}_r{round_num}" if round_num else f"{series_id}_{season}_{event_id}"
        
        # Create sessions (Rallycross typically has heats, semi-finals, finals)
        sessions = self._create_default_sessions(event_id_generated, season)
        
        return Event(
            event_id=event_id_generated,
            series_id=series_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            venue=venue,
            sessions=sessions,
            sources=[Source(
                url=source_url,
                provider_name=self.name,
                retrieved_at=datetime.utcnow(),
                extraction_method="http"
            )]
        )
    
    def _get_timezone_fallback(self, country: str) -> str:
        """Get timezone fallback for countries."""
        # Map countries to their main timezone (sufficient for World RX venues)
        mappings = {
            "Latvia": "Europe/Riga",
            "Hungary": "Europe/Budapest",
            "Sweden": "Europe/Stockholm",
            "Ireland": "Europe/Dublin",
            "France": "Europe/Paris",
            "Portugal": "Europe/Lisbon",
            "United Kingdom": "Europe/London",
            "Great Britain": "Europe/London",
            "Norway": "Europe/Oslo",
            "Germany": "Europe/Berlin",
            "Belgium": "Europe/Brussels",
            "Spain": "Europe/Madrid",
            "Italy": "Europe/Rome",
            "South Africa": "Africa/Johannesburg",
            "Turkey": "Europe/Istanbul",
            "Hong Kong": "Asia/Hong_Kong",
            "China": "Asia/Shanghai",
        }
        return mappings.get(country, "UTC")
    
    def _parse_html(self, payload: RawSeriesPayload, series_id: str, season: int) -> List[Event]:
        """Parse HTML response extracting Next.js flight data."""
        events = []
        
        try:
            html = payload.content
            
            # The data is inside a JS string literal in self.__next_f.push(...)
            # So quotes are escaped as \" and backslashes as \\
            # We look for the start of the events array: \"events\":[
            
            start_pattern = r'\\"events\\":\s*\['
            match = re.search(start_pattern, html)
            
            if not match:
                logger.warning("Could not find events data pattern in World RX HTML")
                return events
            
            # Extract from start of list
            start_index = match.end() - 1 # Include the '['
            
            # Walk forward to find the matching closing bracket
            # Must respect escaped quotes to avoid false positives on brackets inside strings
            current_idx = start_index
            count = 1
            in_inner_string = False
            
            i = start_index + 1
            # Safety limit
            while count > 0 and i < len(html):
                char = html[i]
                
                # Check for escaped char (literal backslash in the html string)
                if char == '\\':
                    if i + 1 < len(html):
                        next_char = html[i+1]
                        
                        # In the raw file (which is a string literal inside script), 
                        # \" represents a quote inside the inner JSON.
                        if next_char == '"':
                            in_inner_string = not in_inner_string
                            i += 2
                            continue
                        
                        # \\ represents a literal backslash inside the inner JSON
                        elif next_char == '\\':
                            i += 2
                            continue
                        
                        # Other escapes like \n
                        else: 
                            i += 2
                            continue
                
                if not in_inner_string:
                    if char == '[':
                        count += 1
                    elif char == ']':
                        count -= 1
                
                i += 1
                
            extracted = html[start_index:i]
            
            # Unescape the string content to make it valid JSON
            unescaped = extracted.replace('\\"', '"').replace('\\\\', '\\')
            
            data = json.loads(unescaped)
            
            seen_ids = set()
            
            for item in data:
                try:
                    # Extract event details
                    event_id = item.get("id")
                    if not event_id or event_id in seen_ids:
                        continue
                        
                    # Handle "Euro RX" label vs potential "World RX"
                    label = item.get('eventLabel', 'Event')
                    country = item.get("eventCountry", "Unknown")
                    name = f"{label} {country}"
                    
                    # Parse dates
                    start_str = item.get("startDate")
                    end_str = item.get("endDate")
                    
                    if not start_str or not end_str:
                        continue
                        
                    start_date = date_parser.parse(start_str).date()
                    end_date = date_parser.parse(end_str).date()
                    
                    # Infer timezone
                    city = "" # City not explicitly in this lightweight object, relying on country
                    timezone_result = infer_timezone_from_location(country, city)
                    
                    if isinstance(timezone_result, tuple):
                        timezone = timezone_result[0]
                    else:
                        timezone = timezone_result
                    
                    # Fallback if inference failed
                    if not timezone:
                        timezone = self._get_timezone_fallback(country)

                    venue = Venue(
                        circuit=country, # Fallback
                        city=city,
                        country=country,
                        timezone=timezone,
                        inferred_timezone=True
                    )
                    
                    # Generate a unique ID for the system
                    # Use a stable slug style ID
                    slug_country = country.lower().replace(' ', '_')
                    system_event_id = f"{series_id}_{season}_{slug_country}"
                    
                    sessions = self._create_default_sessions(system_event_id, season)
                    
                    event = Event(
                        event_id=system_event_id,
                        series_id=series_id,
                        name=name,
                        start_date=start_date,
                        end_date=end_date,
                        venue=venue,
                        sessions=sessions,
                        sources=[Source(
                            url=payload.url,
                            provider_name=self.name,
                            retrieved_at=datetime.utcnow(),
                            extraction_method="http_nextjs_flight"
                        )]
                    )
                    
                    events.append(event)
                    seen_ids.add(event_id)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse inner World RX event item: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Failed to parse World RX HTML: {e}")
        
        return events
    
    def _create_default_sessions(self, event_id: str, season: int) -> List[Session]:
        """Create default sessions for World RX (heats and finals format)."""
        sessions = []
        
        # Rallycross format: Practice, Qualifying Heats, Semi-Finals, Final
        session_info = [
            (SessionType.PRACTICE, "Practice"),
            (SessionType.HEAT, "Qualifying Heat 1"),
            (SessionType.HEAT, "Qualifying Heat 2"),
            (SessionType.HEAT, "Semi-Final 1"),
            (SessionType.HEAT, "Semi-Final 2"),
            (SessionType.RACE, "Final"),
        ]
        
        for idx, (session_type, session_name) in enumerate(session_info):
            sessions.append(
                Session(
                    session_id=f"{event_id}_session_{idx}",
                    type=session_type,
                    name=session_name,
                    start=None,
                    end=None,
                    status=SessionStatus.SCHEDULED
                )
            )
        
        return sessions
