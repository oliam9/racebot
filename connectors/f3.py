"""
FIA Formula 3 Connector.
Scrapes https://www.fiaformula3.com/Calendar for schedule data.
"""
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
import json
import re
import logging
from dateutil import parser as date_parser
from bs4 import BeautifulSoup

from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SeriesCategory, SessionType, SessionStatus
from .base import Connector, RawSeriesPayload
from validators.timezone_utils import infer_timezone_from_location

logger = logging.getLogger(__name__)


class F3Connector(Connector):
    """
    Connector for FIA Formula 3 Championship.
    Uses web scraping with API endpoint detection.
    """
    
    BASE_URL = "https://www.fiaformula3.com"
    CALENDAR_URL = "https://www.fiaformula3.com/Calendar"
    
    @property
    def id(self) -> str:
        return "f3_official"

    @property
    def name(self) -> str:
        return "FIA Formula 3"
        
    def supported_series(self) -> List[SeriesDescriptor]:
        """Return list of supported series."""
        return [
            SeriesDescriptor(
                series_id="f3",
                name="FIA Formula 3 Championship",
                category=SeriesCategory.OPENWHEEL,
                connector_id=self.id
            )
        ]
    
    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        """Fetch F3 season schedule."""
        if series_id != "f3":
            raise ValueError(f"F3 connector does not support series: {series_id}")
        
        # FIA F2/F3 sites often have API endpoints
        # api_endpoints = [
        #     f"{self.BASE_URL}/api/calendar/{season}",
        #     f"{self.BASE_URL}/api/events?season={season}",
        #     f"https://api.fiaformula3.com/v1/event-tracker?seasonYear={season}",
        # ]
        api_endpoints = [] # Force HTML for now as Next.js data is reliable
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True, headers=headers) as client:
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
                resp = client.get(self.CALENDAR_URL)
                resp.raise_for_status()
                
                return RawSeriesPayload(
                    content=resp.text,
                    retrieved_at=datetime.utcnow(),
                    url=self.CALENDAR_URL,
                    content_type="text/html",
                    metadata={"series_id": series_id, "season": season}
                )
                
        except Exception as e:
            logger.error(f"Failed to fetch F3 calendar: {e}")
            raise
    
    def extract(self, payload: RawSeriesPayload) -> List[Event]:
        """Parse F3 season data into Event objects."""
        series_id = payload.metadata.get("series_id", "f3")
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
                    logger.warning(f"Failed to parse F3 event: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to parse F3 JSON: {e}")
        
        return events
    
    def _parse_event_json(self, item: Dict[str, Any], series_id: str, season: int, source_url: str) -> Optional[Event]:
        """Parse a single event from JSON."""
        # Extract basic info
        name = item.get("name", item.get("title", item.get("eventName", "Unknown Event")))
        event_id = item.get("id", item.get("eventId", item.get("meetingKey", "")))
        
        # Extract dates
        start_date = None
        end_date = None
        
        for date_field in ["startDate", "start_date", "date", "dateFrom", "meetingStartDate"]:
            if date_field in item and item[date_field]:
                try:
                    dt = date_parser.parse(str(item[date_field]))
                    start_date = dt.date()
                    break
                except:
                    pass
        
        for date_field in ["endDate", "end_date", "dateTo", "meetingEndDate"]:
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
        
        # Create sessions (F3 typically has practice, qualifying, sprint, feature race)
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
    
    def _parse_html(self, payload: RawSeriesPayload, series_id: str, season: int) -> List[Event]:
        """Parse HTML response."""
        events = []
        
        try:
            html = payload.content
            soup = BeautifulSoup(html, 'lxml')
            
            # 1. Try Next.js data (most reliable for F2/F3 now)
            next_data = soup.find('script', id='__NEXT_DATA__')
            if next_data:
                try:
                    data = json.loads(next_data.string)
                    # Traverse to races: props -> pageProps -> pageData -> Races
                    page_data = data.get('props', {}).get('pageProps', {}).get('pageData', {})
                    races = page_data.get('Races', [])
                    
                    if races:
                        logger.info(f"Found {len(races)} races in Next.js data")
                        for item in races:
                            try:
                                event = self._parse_nextjs_event(item, series_id, season, payload.url)
                                if event:
                                    events.append(event)
                            except Exception as e:
                                logger.warning(f"Failed to parse F3 Next.js event: {e}")
                        return events
                except Exception as e:
                    logger.error(f"Failed to parse __NEXT_DATA__: {e}")
            
            # 2. Legacy/Fallbacks
            # Look for JSON data in script tags (common pattern for modern sites)
            script_pattern = r'<script[^>]*>(.*?)</script>'
            scripts = re.findall(script_pattern, html, re.DOTALL)
            
            for script in scripts:
                # Look for calendar/event data
                if any(keyword in script.lower() for keyword in ['calendar', 'events', 'rounds', 'meetings']):
                    # Try to extract JSON
                    json_patterns = [
                        r'(?:calendar|events|rounds|meetings)\s*[=:]\s*(\[.*?\]);',
                        r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});',
                        r'window\.__DATA__\s*=\s*(\{.*?\});',
                    ]
                    
                    for pattern in json_patterns:
                        matches = re.findall(pattern, script, re.DOTALL)
                        for json_str in matches:
                            try:
                                data = json.loads(json_str)
                                if data:
                                    return self._parse_json(
                                        RawSeriesPayload(
                                            content=json_str,
                                            retrieved_at=payload.retrieved_at,
                                            url=payload.url,
                                            content_type="application/json",
                                            metadata=payload.metadata
                                        ),
                                        series_id,
                                        season
                                    )
                            except:
                                continue
            
            # If no JSON found in scripts, log warning
            logger.warning("F3 HTML parsing requires browser rendering - consider using generic connector")
            
        except Exception as e:
            logger.error(f"Failed to parse F3 HTML: {e}")
        
        return events

    def _parse_nextjs_event(self, item: Dict[str, Any], series_id: str, season: int, source_url: str) -> Optional[Event]:
        """Parse a single event from Next.js structure."""
        # F3 Next.js structure (matches F2):
        # {
        #   "RaceId": 1069,
        #   "RoundNumber": 1,
        #   "RaceStartDate": "2026-03-06",
        #   "RaceEndDate": "2026-03-08",
        #   "CircuitShortName": "Melbourne",
        #   "CircuitName": "Albert Park Circuit",
        #   "CountryName": "Australia",
        #   "Sessions": [...]
        # }

        round_num = item.get("RoundNumber")
        if not round_num:
            return None
            
        name = f"Round {round_num}: {item.get('CircuitShortName', 'Unknown')}"
        event_id = f"{series_id}_{season}_r{round_num}"
        
        # Dates
        try:
            start_date = date_parser.parse(item.get("RaceStartDate")).date()
            end_date_str = item.get("RaceEndDate")
            end_date = date_parser.parse(end_date_str).date() if end_date_str else start_date
        except (ValueError, TypeError):
            # Fallback if dates are missing/invalid
            logger.warning(f"Invalid dates for event {name}")
            return None

        # Venue
        city = item.get("CircuitShortName", "")
        country = item.get("CountryName", "Unknown")
        circuit = item.get("CircuitName", city)
        
        tz_result, tz_inferred = infer_timezone_from_location(country, city)
        timezone = tz_result if tz_result else "UTC"
        
        venue = Venue(
            circuit=circuit,
            city=city,
            country=country,
            timezone=timezone,
            inferred_timezone=tz_inferred
        )

        # Sessions
        sessions = []
        for sess_item in item.get("Sessions", []):
            try:
                # Session mapping
                # SessionCode: PRACTICE, QUALIFYING, RESULT (for races)
                # SessionShortName: Prac 1, Qual, SR (Sprint), FR (Feature)
                
                s_code = sess_item.get("SessionCode", "").upper()
                s_short = sess_item.get("SessionShortName", "").upper()
                s_name = sess_item.get("SessionName", "")
                
                # Determine type
                s_type = SessionType.PRACTICE
                if "QUAL" in s_code or "QUAL" in s_short:
                    s_type = SessionType.QUALIFYING
                elif "RACE" in s_code or "RESULT" in s_code: 
                    if "SR" in s_short or "SPRINT" in s_name.upper():
                        s_type = SessionType.SPRINT
                    elif "FR" in s_short or "FEATURE" in s_name.upper():
                        s_type = SessionType.FEATURE
                    else:
                        s_type = SessionType.RACE
                elif "PRACTICE" in s_code:
                     s_type = SessionType.PRACTICE

                # Timestamps
                start_time = None
                end_time = None
                
                if sess_item.get("SessionStartTime"):
                    start_time = date_parser.parse(sess_item.get("SessionStartTime")).isoformat()
                
                if sess_item.get("SessionEndTime"):
                    end_time = date_parser.parse(sess_item.get("SessionEndTime")).isoformat()
                
                # Status
                status = SessionStatus.SCHEDULED
                if sess_item.get("Unconfirmed"):
                    # keep scheduled since we have times
                    pass

                session_id = f"{event_id}_{s_short.replace(' ', '').lower()}_{sess_item.get('SessionId')}"

                sessions.append(Session(
                    session_id=session_id,
                    type=s_type,
                    name=s_name,
                    start=start_time,
                    end=end_time,
                    status=status
                ))

            except Exception as e:
                logger.warning(f"Failed to parse session {sess_item.get('SessionName')}: {e}")

        # If no sessions parsed, create defaults (fallback)
        if not sessions:
            sessions = self._create_default_sessions(event_id, season)

        return Event(
            event_id=event_id,
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
                extraction_method="nextjs_html"
            )]
        )
    
    def _create_default_sessions(self, event_id: str, season: int) -> List[Session]:
        """Create default sessions for F3 (typically support race format)."""
        sessions = []
        
        # F3 format: Practice, Qualifying, Sprint Race, Feature Race
        session_info = [
            (SessionType.PRACTICE, "Practice"),
            (SessionType.QUALIFYING, "Qualifying"),
            (SessionType.SPRINT, "Sprint Race"),
            (SessionType.FEATURE, "Feature Race"),
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
