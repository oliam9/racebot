"""
DTM (Deutsche Tourenwagen Masters) Connector.
Uses Playwright to render https://www.dtm.com/en/events and extract calendar data.
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


class DTMConnector(Connector):
    """
    Connector for DTM series.
    Uses Playwright for JavaScript rendering to extract calendar data.
    """
    
    BASE_URL = "https://www.dtm.com"
    EVENTS_URL = "https://www.dtm.com/en/events"
    
    @property
    def id(self) -> str:
        return "dtm_official"

    @property
    def name(self) -> str:
        return "DTM Official"
        
    def supported_series(self) -> List[SeriesDescriptor]:
        """Return list of supported series."""
        return [
            SeriesDescriptor(
                series_id="dtm",
                name="DTM",
                category=SeriesCategory.TOURING,
                connector_id=self.id
            )
        ]
    
    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        """Fetch DTM season schedule using Playwright."""
        if series_id != "dtm":
            raise ValueError(f"DTM connector does not support series: {series_id}")
        
        if not self.playwright_enabled:
            logger.warning("Playwright disabled, falling back to basic HTTP")
            return self._fetch_basic_http(season)
        
        try:
            # Use Playwright to render the page
            # Try to use existing event loop, or create new one with proper policy
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Event loop is already running (e.g., in Streamlit)
                    # We need to run async code in a separate thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self._fetch_with_playwright())
                        html = future.result(timeout=60)
                else:
                    html = loop.run_until_complete(self._fetch_with_playwright())
            except RuntimeError:
                # No event loop, create one
                html = asyncio.run(self._fetch_with_playwright())
            
            return RawSeriesPayload(
                content=html,
                retrieved_at=datetime.utcnow(),
                url=self.EVENTS_URL,
                content_type="text/html",
                metadata={"series_id": series_id, "season": season, "rendered": True}
            )
                
        except Exception as e:
            logger.error(f"Failed to fetch DTM calendar with Playwright: {e}")
            # Fall back to basic HTTP
            return self._fetch_basic_http(season)
    
    async def _fetch_with_playwright(self) -> str:
        """Fetch page content using Playwright."""
        try:
            from browser_client import fetch_rendered_with_retry
            
            logger.info(f"Rendering DTM page with Playwright: {self.EVENTS_URL}")
            rendered = await fetch_rendered_with_retry(self.EVENTS_URL)
            return rendered.content
            
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
                resp = client.get(self.EVENTS_URL)
                resp.raise_for_status()
                
                return RawSeriesPayload(
                    content=resp.text,
                    retrieved_at=datetime.utcnow(),
                    url=self.EVENTS_URL,
                    content_type="text/html",
                    metadata={"series_id": "dtm", "season": season, "rendered": False}
                )
        except Exception as e:
            logger.error(f"Basic HTTP fetch failed: {e}")
            raise
    
    def extract(self, payload: RawSeriesPayload) -> List[Event]:
        """Parse DTM season data into Event objects."""
        series_id = payload.metadata.get("series_id", "dtm")
        season = payload.metadata.get("season", datetime.now().year)
        
        # Check if this is rendered HTML
        was_rendered = payload.metadata.get("rendered", False)
        if not was_rendered and len(payload.content) < 50000:
            logger.warning(
                f"DTM HTML appears to be un-rendered ({len(payload.content)} bytes). "
                f"Playwright is required for DTM. Enable with PLAYWRIGHT_ENABLED=true "
                f"and ensure playwright browsers are installed: playwright install chromium"
            )
        
        # Try to parse the HTML content
        return self._parse_html(payload, series_id, season)
    
    def _parse_html(self, payload: RawSeriesPayload, series_id: str, season: int) -> List[Event]:
        """Parse HTML response - look for embedded JSON or DOM elements."""
        events = []
        html = payload.content
        
        try:
            # Strategy 1: Look for JSON in <script> tags
            script_pattern = r'<script[^>]*>(.*?)</script>'
            scripts = re.findall(script_pattern, html, re.DOTALL | re.IGNORECASE)
            
            for script in scripts:
                # Look for calendar/event data patterns
                json_patterns = [
                    r'events["\']?\s*[:=]\s*(\[.*?\])',
                    r'calendar["\']?\s*[:=]\s*(\[.*?\])',
                    r'__INITIAL_STATE__\s*=\s*(\{.*?\});',
                    r'__DATA__\s*=\s*(\{.*?\});',
                    r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});',
                ]
                
                for pattern in json_patterns:
                    matches = re.findall(pattern, script, re.DOTALL)
                    for json_str in matches:
                        try:
                            data = json.loads(json_str)
                            parsed_events = self._extract_from_json(data, series_id, season, payload.url)
                            if parsed_events:
                                events.extend(parsed_events)
                                logger.info(f"Extracted {len(parsed_events)} events from embedded JSON")
                                return events
                        except:
                            continue
            
            # Strategy 2: Parse DOM elements (if rendered)
            dom_events = self._parse_dom_elements(html, series_id, season, payload.url)
            if dom_events:
                events.extend(dom_events)
                logger.info(f"Extracted {len(dom_events)} events from DOM")
                return events
            
            # Strategy 3: Look for any date patterns
            fallback_events = self._extract_fallback_dates(html, series_id, season, payload.url)
            if fallback_events:
                events.extend(fallback_events)
                logger.info(f"Extracted {len(fallback_events)} events from date patterns")
                return events
            
            if not events:
                logger.warning("DTM HTML parsing found no events - page may require full browser rendering")
            
        except Exception as e:
            logger.error(f"Failed to parse DTM HTML: {e}")
        
        return events
    
    def _extract_from_json(self, data: Any, series_id: str, season: int, source_url: str) -> List[Event]:
        """Extract events from JSON data structure."""
        events = []
        
        # Handle various JSON structures
        events_list = []
        if isinstance(data, list):
            events_list = data
        elif isinstance(data, dict):
            events_list = data.get("events", data.get("calendar", data.get("races", [])))
        
        for item in events_list:
            if isinstance(item, dict):
                event = self._parse_event_json(item, series_id, season, source_url)
                if event:
                    events.append(event)
        
        return events
    
    def _parse_dom_elements(self, html: str, series_id: str, season: int, source_url: str) -> List[Event]:
        """Parse event data from rendered DOM using BeautifulSoup."""
        events = []
        
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'lxml')
            
            # DTM website structure: events are in elements with event info
            # Look for event containers
            event_containers = soup.find_all('div', class_='event-list__container')
            
            if not event_containers:
                # Try alternative patterns
                event_containers = soup.find_all(['article', 'div'], class_=lambda x: x and ('event' in x.lower() or 'race' in x.lower()))
            
            logger.info(f"Found {len(event_containers)} event containers")
            
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }
            
            for idx, container in enumerate(event_containers):
                try:
                    # Check if this event is for the correct season
                    # Look for "DTM 2026" or similar year identifier
                    container_text = container.get_text(strip=True)
                    
                    # Skip if this event is not for the requested season
                    season_label = f"DTM {season}"
                    if season_label not in container_text:
                        logger.debug(f"Skipping event - not for season {season}")
                        continue
                    
                    # Extract round number
                    round_elem = container.find(text=re.compile(r'\d{2}'))
                    round_num = len(events) + 1  # Use actual event count, not container index
                    if round_elem:
                        match = re.search(r'(\d{2})', str(round_elem))
                        if match:
                            round_num = int(match.group(1))
                    
                    # Extract dates - look for patterns like "24. - 26." and "Apr"
                    date_text = ""
                    month_text = ""
                    
                    # Find date range (e.g., "24. - 26.")
                    date_elem = container.find(class_='h4')
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                    
                    # Find month (e.g., "Apr")
                    month_elems = container.find_all(class_='text-uppercase')
                    for elem in month_elems:
                        text = elem.get_text(strip=True).lower()
                        if text[:3] in month_map:
                            month_text = text
                            break
                    
                    # Find circuit name - it's in the text after the round number
                    # Text structure: DTM 2026 / 24. - 26. / Apr / 01 / Red Bull Ring / more info
                    circuit = "TBC"
                    text_lines = [line.strip() for line in container.get_text(separator='\n', strip=True).split('\n') if line.strip()]
                    
                    # Look for the circuit name - it's typically after the round number and before "more info"
                    for i, line in enumerate(text_lines):
                        # Check for round number first (before length check)
                        if re.match(r'^\d{2}$', line):  # Round number (01, 02, etc.)
                            # Circuit name should be next
                            if i + 1 < len(text_lines):
                                circuit = text_lines[i + 1]
                                break
                    
                    # Parse dates
                    start_date = None
                    end_date = None
                    
                    if date_text and month_text:
                        # Pattern: "24. - 26." "Apr"
                        date_match = re.search(r'(\d{1,2})\.\s*-\s*(\d{1,2})\.', date_text)
                        if date_match:
                            start_day = int(date_match.group(1))
                            end_day = int(date_match.group(2))
                            month_num = month_map.get(month_text[:3].lower())
                            
                            if month_num:
                                start_date = date(season, month_num, start_day)
                                end_date = date(season, month_num, end_day)
                    
                    if not start_date:
                        logger.debug(f"Could not parse dates for event {idx+1}: date_text='{date_text}', month_text='{month_text}'")
                        continue
                    
                    # Infer country and timezone from circuit name
                    country = "Germany"  # Default for DTM
                    if "austria" in circuit.lower() or "red bull ring" in circuit.lower():
                        country = "Austria"
                    elif "italy" in circuit.lower() or "monza" in circuit.lower() or "imola" in circuit.lower():
                        country = "Italy"
                    elif "netherlands" in circuit.lower() or "assen" in circuit.lower() or "zandvoort" in circuit.lower():
                        country = "Netherlands"
                    elif "belgium" in circuit.lower() or "spa" in circuit.lower() or "zolder" in circuit.lower():
                        country = "Belgium"
                    
                    # infer_timezone_from_location returns (timezone, was_inferred)
                    timezone, was_inferred = infer_timezone_from_location(country, None)
                    if not timezone:
                        # Fallback to Central European Time
                        timezone = "Europe/Berlin"
                        was_inferred = True
                    
                    # Create event
                    event_id = f"dtm_{season}_r{round_num}"
                    event = Event(
                        event_id=event_id,
                        series_id=series_id,
                        name=f"DTM {circuit}",
                        start_date=start_date,
                        end_date=end_date,
                        venue=Venue(
                            circuit=circuit,
                            city=None,
                            country=country,
                            timezone=timezone,
                            inferred_timezone=was_inferred
                        ),
                        sessions=[], # self._create_default_sessions(event_id, season),
                        sources=[Source(
                            url=source_url,
                            provider_name=self.name,
                            retrieved_at=datetime.utcnow(),
                            extraction_method="dom_parsing"
                        )]
                    )
                    
                    events.append(event)
                    logger.debug(f"Extracted: {event.name} at {circuit} on {start_date}")
                    
                except Exception as e:
                    logger.warning(f"Failed to parse event container {idx}: {e}")
                    continue
            
        except ImportError:
            logger.error("BeautifulSoup not available for DOM parsing")
        except Exception as e:
            logger.error(f"DOM parsing error: {e}", exc_info=True)
        
        return events
    
    def _extract_fallback_dates(self, html: str, series_id: str, season: int, source_url: str) -> List[Event]:
        """Extract basic event info from any visible dates in HTML."""
        events = []
        
        # Look for 2026 dates
        date_pattern = r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*[-–]\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})'
        matches = re.findall(date_pattern, html, re.IGNORECASE)
        
        month_map = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        
        for match in matches:
            try:
                start_day, start_month, end_day, end_month, year = match
                year = int(year)
                
                if year != season:
                    continue
                
                start_month_num = month_map.get(start_month.lower()[:3])
                end_month_num = month_map.get(end_month.lower()[:3])
                
                if start_month_num and end_month_num:
                    start_date = date(year, start_month_num, int(start_day))
                    end_date = date(year, end_month_num, int(end_day))
                    
                    # Create basic event
                    event_id = f"dtm_{year}_r{len(events)+1}"
                    events.append(Event(
                        event_id=event_id,
                        series_id=series_id,
                        name=f"DTM Round {len(events)+1}",
                        start_date=start_date,
                        end_date=end_date,
                        venue=Venue(
                            circuit="TBC",
                            city=None,
                            country="TBC",
                            timezone="Europe/Berlin",
                            inferred_timezone=True
                        ),
                        sessions=[], # self._create_default_sessions(event_id, season),
                        sources=[Source(
                            url=source_url,
                            provider_name=self.name,
                            retrieved_at=datetime.utcnow(),
                            extraction_method="date_pattern"
                        )]
                    ))
            except Exception as e:
                logger.debug(f"Failed to parse date pattern: {e}")
                continue
        
        return events
    
    def _parse_event_json(self, item: Dict[str, Any], series_id: str, season: int, source_url: str) -> Optional[Event]:
        """Parse a single event from JSON."""
        # Extract basic info
        name = item.get("name", item.get("title", "Unknown Event"))
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
        
        # Create sessions (DTM typically has practice, qualifying, races)
        sessions = [] # self._create_default_sessions(event_id, season)
        
        # Generate event_id
        round_num = item.get("round", item.get("roundNumber", 0))
        event_id_generated = f"dtm_{season}_r{round_num}" if round_num else f"dtm_{season}_{event_id}"
        
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
    
    def _create_default_sessions(self, event_id: str, season: int) -> List[Session]:
        """Create default sessions for DTM (typically 2-3 day event)."""
        sessions = []
        
        # DTM usually has: Practice, Qualifying, Race 1, Race 2
        session_info = [
            (SessionType.PRACTICE, "Practice"),
            (SessionType.QUALIFYING, "Qualifying"),
            (SessionType.RACE, "Race 1"),
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
