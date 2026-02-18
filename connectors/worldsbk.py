"""
FIM Superbike World Championship (WorldSBK) Connector.
Scrapes https://www.worldsbk.com/en/calendar for schedule data.
Uses Playwright to render JavaScript-based calendar.
"""
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
import json
import re
import logging
import asyncio
from dateutil import parser as date_parser

from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SeriesCategory, SessionType, SessionStatus
from .base import Connector, RawSeriesPayload
from validators.timezone_utils import infer_timezone_from_location

logger = logging.getLogger(__name__)


class WorldSBKConnector(Connector):
    """
    Connector for FIM Superbike World Championship.
    Uses Playwright for JavaScript rendering to extract calendar data.
    """
    
    BASE_URL = "https://www.worldsbk.com"
    CALENDAR_URL = "https://www.worldsbk.com/en/calendar"
    
    @property
    def id(self) -> str:
        return "worldsbk_official"

    @property
    def name(self) -> str:
        return "FIM Superbike World Championship"
        
    def supported_series(self) -> List[SeriesDescriptor]:
        """Return list of supported series."""
        return [
            SeriesDescriptor(
                series_id="worldsbk",
                name="FIM Superbike World Championship",
                category=SeriesCategory.MOTORCYCLE,
                connector_id=self.id
            )
        ]
    
    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        """Fetch WorldSBK season schedule using Playwright."""
        if series_id != "worldsbk":
            raise ValueError(f"WorldSBK connector does not support series: {series_id}")
        
        if not self.playwright_enabled:
            logger.warning("Playwright disabled, falling back to basic HTTP")
            return self._fetch_basic_http(season)
        
        try:
            # Use Playwright to render the page
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self._fetch_with_playwright())
                        html = future.result(timeout=60)
                        # We should try to cleanup the browser in that thread/loop if possible
                        # But since we can't easily run cleanup in that finished loop/thread
                        # We rely on the thread dying.
                        # However, Playwright process might hang if not closed.
                        # The executor.submit creates a fresh loop via asyncio.run
                        # Let's modify _fetch_with_playwright to cleanup itself if it created the pool.
                        pass
                else:
                    html = loop.run_until_complete(self._fetch_with_playwright())
            except RuntimeError:
                html = asyncio.run(self._fetch_with_playwright())
            
            return RawSeriesPayload(
                content=html,
                retrieved_at=datetime.utcnow(),
                url=self.CALENDAR_URL,
                content_type="text/html",
                metadata={"series_id": series_id, "season": season, "rendered": True}
            )
                
        except Exception as e:
            logger.error(f"Failed to fetch WorldSBK calendar with Playwright: {e}")
            return self._fetch_basic_http(season)
    
    async def _fetch_with_playwright(self) -> str:
        """Fetch page content using Playwright."""
        try:
            from browser_client import fetch_rendered_with_retry, cleanup_browser
            
            logger.info(f"Rendering WorldSBK page with Playwright: {self.CALENDAR_URL}")
            try:
                rendered = await fetch_rendered_with_retry(self.CALENDAR_URL)
                return rendered.content
            finally:
                # If we are running in a short-lived loop (e.g. from the executor),
                # we should cleanup the browser instance for this loop.
                # We can detect if we are in the main thread or not?
                # For now, let's just always cleanup if we are in this specific method
                # which is called via asyncio.run in a separate thread.
                # Wait, if we are in the main loop (line 70), we do NOT want to cleanup
                # because we might want to reuse it.
                # But line 67 does run it in a separate thread/loop.
                
                # Check if we are running in a separate thread
                import threading
                if threading.current_thread() != threading.main_thread():
                    await cleanup_browser()
            
        except ImportError:
            logger.error("browser_client not available")
            raise
        except Exception as e:
            logger.error(f"Playwright rendering failed: {e}")
            raise
    
    def _fetch_basic_http(self, season: int) -> RawSeriesPayload:
        """Fallback to basic HTTP fetch."""
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                resp = client.get(self.CALENDAR_URL)
                resp.raise_for_status()
                
                return RawSeriesPayload(
                    content=resp.text,
                    retrieved_at=datetime.utcnow(),
                    url=self.CALENDAR_URL,
                    content_type="text/html",
                    metadata={"series_id": "worldsbk", "season": season, "rendered": False}
                )
        except Exception as e:
            logger.error(f"Basic HTTP fetch failed: {e}")
            raise
    
    def extract(self, payload: RawSeriesPayload) -> List[Event]:
        """Parse WorldSBK season data into Event objects."""
        series_id = payload.metadata.get("series_id", "worldsbk")
        season = payload.metadata.get("season", datetime.now().year)
        
        was_rendered = payload.metadata.get("rendered", False)
        if not was_rendered and len(payload.content) < 50000:
            logger.warning(
                f"WorldSBK HTML appears to be un-rendered ({len(payload.content)} bytes). "
                f"Playwright is required for WorldSBK."
            )
        
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
                    logger.warning(f"Failed to parse WorldSBK event: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to parse WorldSBK JSON: {e}")
        
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
        
        # Create sessions (WorldSBK has practice, superpole, race 1, superpole race, race 2)
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
        """Parse HTML response using BeautifulSoup."""
        events = []
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(payload.content, 'lxml')
            
            # WorldSBK structure: each event is in a calendar-round-item
            event_containers = soup.find_all(class_='calendar-round-item')
            
            logger.info(f"Found {len(event_containers)} WorldSBK event containers")
            
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }
            
            country_map = {
                'aus': 'Australia', 'por': 'Portugal', 'ned': 'Netherlands', 
                'hun': 'Hungary', 'cze': 'Czech Republic', 'esp': 'Spain',
                'ita': 'Italy', 'gbr': 'United Kingdom', 'fra': 'France',
                'usa': 'United States', 'arg': 'Argentina', 'jpn': 'Japan',
                'idn': 'Indonesia', 'ind': 'India', 'ger': 'Germany',
                'aut': 'Austria', 'bel': 'Belgium', 'bra': 'Brazil'
            }
            
            for container in event_containers:
                try:
                    # Extract event data
                    event_data = container.find(class_='event-data')
                    if not event_data:
                        continue
                    
                    # Get round number
                    round_span = event_data.find('span', class_='round')
                    if not round_span:
                        continue
                    
                    round_text = round_span.get_text(strip=True)  # e.g., "Round-1"
                    round_match = re.search(r'(\d+)', round_text)
                    round_num = int(round_match.group(1)) if round_match else len(events) + 1
                    
                    # Get event name
                    h2 = event_data.find('h2')
                    event_name = h2.get_text(strip=True) if h2 else f"Round {round_num}"
                    
                    # Get country from flag class
                    country = "Unknown"
                    for cls in round_span.get('class', []):
                        if cls in country_map:
                            country = country_map[cls]
                            break
                    
                    # Fallback: infer from event name
                    if country == "Unknown":
                        name_lower = event_name.lower()
                        if 'spanish' in name_lower or 'aragon' in name_lower or 'jerez' in name_lower or 'barcelona' in name_lower:
                            country = "Spain"
                        elif 'italian' in name_lower or 'misano' in name_lower or 'mugello' in name_lower:
                            country = "Italy"
                        elif 'estoril' in name_lower or 'portimao' in name_lower:
                            country = "Portugal"
                        elif 'french' in name_lower or 'magny' in name_lower:
                            country = "France"
                        elif 'british' in name_lower or 'donington' in name_lower or 'silverstone' in name_lower:
                            country = "United Kingdom"
                    
                    # Get dates - format is "20 - 22 Feb" or similar
                    dates_text = container.get_text(separator=' ', strip=True)
                    
                    # Pattern: DD - DD Mon (e.g., "20 - 22 Feb")
                    date_match = re.search(r'(\d{1,2})\s*-\s*(\d{1,2})\s+(\w{3})', dates_text)
                    
                    if not date_match:
                        logger.debug(f"Could not parse dates for {event_name}")
                        continue
                    
                    start_day = int(date_match.group(1))
                    end_day = int(date_match.group(2))
                    month_abbr = date_match.group(3).lower()
                    
                    month_num = month_map.get(month_abbr)
                    if not month_num:
                        logger.debug(f"Unknown month: {month_abbr}")
                        continue
                    
                    start_date = date(season, month_num, start_day)
                    end_date = date(season, month_num, end_day)
                    
                    # Infer timezone from country
                    timezone, was_inferred = infer_timezone_from_location(country, None)
                    if not timezone:
                        # Default fallback based on country
                        if country == "Australia":
                            timezone = "Australia/Melbourne"
                        elif country == "Indonesia":
                            timezone = "Asia/Jakarta"
                        elif country == "Argentina":
                            timezone = "America/Argentina/Buenos_Aires"
                        else:
                            timezone = "Europe/Rome"  # Most WorldSBK races are in Europe
                        was_inferred = True
                    
                    # Determine circuit name
                    circuit_name = self.CIRCUIT_MAP.get(event_name)
                    
                    # Try partial match if exact match fails
                    if not circuit_name:
                        for key, val in self.CIRCUIT_MAP.items():
                            if key in event_name:
                                circuit_name = val
                                break
                    
                    # Fallback
                    if not circuit_name:
                        circuit_name = event_name

                    # Create event
                    event_id = f"worldsbk_{season}_r{round_num}"
                    event = Event(
                        event_id=event_id,
                        series_id=series_id,
                        name=f"WorldSBK {event_name}",
                        start_date=start_date,
                        end_date=end_date,
                        venue=Venue(
                            circuit=circuit_name,
                            city=None,
                            country=country,
                            timezone=timezone,
                            inferred_timezone=was_inferred
                        ),
                        sessions=[], # self._create_default_sessions(event_id, season),
                        sources=[Source(
                            url=payload.url,
                            provider_name=self.name,
                            retrieved_at=datetime.utcnow(),
                            extraction_method="dom_parsing"
                        )]
                    )
                    
                    events.append(event)
                    logger.debug(f"Extracted: {event.name} on {start_date}")
                    
                except Exception as e:
                    logger.warning(f"Failed to parse WorldSBK event: {e}")
                    continue
            
        except ImportError:
            logger.error("BeautifulSoup not available for DOM parsing")
        except Exception as e:
            logger.error(f"WorldSBK DOM parsing error: {e}", exc_info=True)
        
        return events
    
    # Mapping from Round Name/Country to Circuit Name
    CIRCUIT_MAP = {
        "Australian Round": "Phillip Island Grand Prix Circuit",
        "Pirelli Portuguese Round": "Autódromo Internacional do Algarve",
        "Portuguese Round": "Autódromo Internacional do Algarve",
        "Pirelli Dutch Round": "TT Circuit Assen",
        "Dutch Round": "TT Circuit Assen",
        "Motul Hungarian Round": "Balaton Park Circuit",
        "Hungarian Round": "Balaton Park Circuit",
        "Czech Round": "Autodrom Most",
        "Aragon Round": "MotorLand Aragón",
        "Pirelli Emilia Romagna Round": "Misano World Circuit Marco Simoncelli",
        "Emilia Romagna Round": "Misano World Circuit Marco Simoncelli",
        "Prosecco DOC UK Round": "Donington Park",
        "UK Round": "Donington Park",
        "Acerbis French Round": "Circuit de Nevers Magny-Cours",
        "French Round": "Circuit de Nevers Magny-Cours",
        "Italian Round": "Cremona Circuit",
        "Tissot Estoril Round": "Circuito Estoril",
        "Estoril Round": "Circuito Estoril",
        "Pirelli Spanish Round": "Circuito de Jerez - Ángel Nieto",
        "Spanish Round": "Circuito de Jerez - Ángel Nieto",
    }

    def _create_default_sessions(self, event_id: str, season: int) -> List[Session]:
        """Create default sessions for WorldSBK (typical 3-day format)."""
        sessions = []
        
        # WorldSBK format per user request
        session_info = [
            (SessionType.PRACTICE, "Free Practice 1"),
            (SessionType.PRACTICE, "Free Practice 2"),
            (SessionType.PRACTICE, "Free Practice 3"),
            (SessionType.QUALIFYING, "Superpole"),
            (SessionType.RACE, "Race 1"),
            (SessionType.PRACTICE, "Warm-Up"),
            (SessionType.SPRINT, "Superpole Race"),
            (SessionType.RACE, "Race 2"),
        ]
        
        for idx, (session_type, session_name) in enumerate(session_info):
            sessions.append(
                Session(
                    session_id=f"{event_id}_session_{idx}",
                    type=session_type,
                    name=session_name,
                    start=None,
                    end="TBC",
                    status=SessionStatus.SCHEDULED
                )
            )
        
        return sessions
