"""
GT World Challenge Connectors (SRO platform).
Three regional series + Intercontinental GT Challenge — all on SRO websites.
"""
from datetime import datetime, date
from typing import List
import httpx
import re
import logging
import asyncio
from bs4 import BeautifulSoup

from models.schema import Event, Venue, Source, SeriesDescriptor
from models.enums import SeriesCategory
from .base import Connector, RawSeriesPayload
from validators.timezone_utils import infer_timezone_from_location

logger = logging.getLogger(__name__)


class _SROBaseConnector(Connector):
    """Base for all SRO GT World Challenge connectors — shared DOM parsing."""

    SCHEDULE_URL: str = ""
    _SERIES_ID: str = ""
    _SERIES_NAME: str = ""
    _DEFAULT_TZ: str = "Europe/Paris"

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != self._SERIES_ID:
            raise ValueError(f"{self.name} does not support: {series_id}")
        html, method = "", "http"
        if self.playwright_enabled:
            try:
                html = self._pw()
                method = "playwright"
            except Exception as e:
                logger.warning("Playwright failed for %s: %s", self.name, e)
        if not html:
            resp = httpx.get(self.SCHEDULE_URL, headers={"User-Agent": "Mozilla/5.0"},
                             timeout=15, follow_redirects=True)
            html = resp.text
        return RawSeriesPayload(content=html, content_type="text/html", url=self.SCHEDULE_URL,
                                retrieved_at=datetime.utcnow(),
                                metadata={"series_id": series_id, "season": season, "method": method})

    def _pw(self):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as ex:
                    return ex.submit(asyncio.run, self._render()).result(timeout=60)
            return loop.run_until_complete(self._render())
        except RuntimeError:
            return asyncio.run(self._render())

    async def _render(self):
        from browser_client import fetch_rendered_with_retry
        return (await fetch_rendered_with_retry(self.SCHEDULE_URL)).content

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        season = raw.metadata.get("season", datetime.now().year)
        events = []
        soup = BeautifulSoup(raw.content, "html.parser")
        mm = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}

        containers = soup.find_all(["article","div","a","section","li"],
            class_=lambda c: c and any(k in c.lower() for k in ["event","race","round","calendar","card"]))
        if not containers:
            containers = soup.find_all("a", href=re.compile(r"/race/|/event/|/round/"))

        for idx, c in enumerate(containers, 1):
            try:
                text = c.get_text(separator="\n", strip=True)
                if len(text) < 5: continue
                dm = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text, re.I)
                if not dm:
                    dm = re.search(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text, re.I)
                if not dm: continue
                g = dm.groups()
                if len(g)==3: sd,ed,mo = int(g[0]),int(g[1]),mm.get(g[2][:3].lower(),0)
                else: sd,ed,mo = int(g[0]),int(g[0]),mm.get(g[1][:3].lower(),0)
                if not mo: continue
                lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip())>3 and not re.match(r"^\d",l.strip())]
                name = lines[0][:60] if lines else f"{self._SERIES_NAME} Rd {idx}"
                tz, _ = infer_timezone_from_location(city=name, country="")
                events.append(Event(
                    event_id=f"{self._SERIES_ID}_{season}_r{idx}", series_id=self._SERIES_ID, name=name,
                    start_date=date(season,mo,sd), end_date=date(season,mo,ed),
                    venue=Venue(circuit=name, city=None, country="Unknown", timezone=tz or self._DEFAULT_TZ),
                    sessions=[],
                    sources=[Source(url=raw.url, provider_name=self.name,
                                   retrieved_at=raw.retrieved_at, extraction_method=raw.metadata.get("method","http"))],
                ))
            except Exception as e:
                logger.debug("%s event %d: %s", self._SERIES_ID, idx, e)
        logger.info("%s: %d events for %d", self._SERIES_NAME, len(events), season)
        return events


class GTWCEuropeConnector(_SROBaseConnector):
    """GT World Challenge Europe."""
    SCHEDULE_URL = "https://www.gt-world-challenge-europe.com/calendar"
    _SERIES_ID = "gtwc_europe"
    _SERIES_NAME = "GT World Challenge Europe"
    _DEFAULT_TZ = "Europe/Paris"

    @property
    def id(self): return "gtwc_europe_official"
    @property
    def name(self): return "GTWC Europe Official"
    def supported_series(self):
        return [SeriesDescriptor(series_id="gtwc_europe", name="GT World Challenge Europe",
                                 category=SeriesCategory.GT, connector_id=self.id)]


class GTWCAmericaConnector(_SROBaseConnector):
    """GT World Challenge America."""
    SCHEDULE_URL = "https://www.gt-world-challenge-america.com/calendar"
    _SERIES_ID = "gtwc_america"
    _SERIES_NAME = "GT World Challenge America"
    _DEFAULT_TZ = "America/New_York"

    @property
    def id(self): return "gtwc_america_official"
    @property
    def name(self): return "GTWC America Official"
    def supported_series(self):
        return [SeriesDescriptor(series_id="gtwc_america", name="GT World Challenge America",
                                 category=SeriesCategory.GT, connector_id=self.id)]


class GTWCAsiaConnector(_SROBaseConnector):
    """GT World Challenge Asia."""
    SCHEDULE_URL = "https://www.gtw-challenge-asia.com/calendar"
    _SERIES_ID = "gtwc_asia"
    _SERIES_NAME = "GT World Challenge Asia"
    _DEFAULT_TZ = "Asia/Shanghai"

    @property
    def id(self): return "gtwc_asia_official"
    @property
    def name(self): return "GTWC Asia Official"
    def supported_series(self):
        return [SeriesDescriptor(series_id="gtwc_asia", name="GT World Challenge Asia",
                                 category=SeriesCategory.GT, connector_id=self.id)]


class IGTCConnector(_SROBaseConnector):
    """Intercontinental GT Challenge."""
    SCHEDULE_URL = "https://www.intercontinentalgtchallenge.com/calendar"
    _SERIES_ID = "igtc"
    _SERIES_NAME = "Intercontinental GT Challenge"
    _DEFAULT_TZ = "UTC"

    @property
    def id(self): return "igtc_official"
    @property
    def name(self): return "IGTC Official"
    def supported_series(self):
        return [SeriesDescriptor(series_id="igtc", name="Intercontinental GT Challenge",
                                 category=SeriesCategory.GT, connector_id=self.id)]
