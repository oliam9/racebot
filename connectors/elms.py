"""
European Le Mans Series (ELMS) Connector.
Uses Playwright for fiawec.com-style platform.
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


class ELMSConnector(Connector):
    """Connector for European Le Mans Series."""

    SCHEDULE_URL = "https://www.europeanlemansseries.com/en/season/calendar"

    @property
    def id(self) -> str:
        return "elms_official"

    @property
    def name(self) -> str:
        return "ELMS Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [SeriesDescriptor(series_id="elms", name="European Le Mans Series",
                                 category=SeriesCategory.ENDURANCE, connector_id=self.id)]

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "elms":
            raise ValueError(f"ELMS connector does not support: {series_id}")
        html, method = self._fetch_html()
        return RawSeriesPayload(content=html, content_type="text/html", url=self.SCHEDULE_URL,
                                retrieved_at=datetime.utcnow(),
                                metadata={"series_id": series_id, "season": season, "method": method})

    def _fetch_html(self):
        if self.playwright_enabled:
            try:
                return self._pw(), "playwright"
            except Exception as e:
                logger.warning("Playwright failed for ELMS: %s", e)
        resp = httpx.get(self.SCHEDULE_URL, headers={"User-Agent": "Mozilla/5.0"},
                         timeout=15, follow_redirects=True)
        return resp.text, "http"

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
        return self._parse(raw.content, season, raw)

    def _parse(self, html, season, raw):
        events = []
        soup = BeautifulSoup(html, "html.parser")
        mm = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}

        containers = soup.find_all(["article","div","a","section"],
            class_=lambda c: c and any(k in c.lower() for k in ["event","race","round","calendar"]))
        if not containers:
            containers = soup.find_all("a", href=re.compile(r"/race/|/event/"))

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
                name = lines[0][:60] if lines else f"ELMS Rd {idx}"
                tz, _ = infer_timezone_from_location(city=name, country="")
                events.append(Event(
                    event_id=f"elms_{season}_r{idx}", series_id="elms", name=name,
                    start_date=date(season,mo,sd), end_date=date(season,mo,ed),
                    venue=Venue(circuit=name, city=None, country="Unknown", timezone=tz or "Europe/Paris"),
                    sessions=[],
                    sources=[Source(url=raw.url, provider_name=self.name,
                                   retrieved_at=raw.retrieved_at, extraction_method=raw.metadata.get("method","http"))],
                ))
            except Exception as e:
                logger.debug("ELMS event %d: %s", idx, e)
        logger.info("ELMS: %d events for %d", len(events), season)
        return events
