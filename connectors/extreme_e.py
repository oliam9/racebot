"""
Extreme E Connector.
Note: Extreme E ended; series replaced by Extreme H (hydrogen).
Keeping for historical/legacy data.
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


class ExtremeEConnector(Connector):
    """Connector for Extreme E (legacy — series ended 2024)."""

    SCHEDULE_URL = "https://www.extreme-e.com/calendar"

    @property
    def id(self) -> str:
        return "extreme_e_official"

    @property
    def name(self) -> str:
        return "Extreme E Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [SeriesDescriptor(series_id="extreme_e", name="Extreme E",
                                 category=SeriesCategory.OTHER, connector_id=self.id)]

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "extreme_e":
            raise ValueError(f"Extreme E connector does not support: {series_id}")
        html, method = "", "http"
        urls = [self.SCHEDULE_URL, "https://www.extreme-e.com/"]
        if self.playwright_enabled:
            try:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as ex:
                            html = ex.submit(asyncio.run, self._render(urls[0])).result(timeout=60)
                    else:
                        html = loop.run_until_complete(self._render(urls[0]))
                except RuntimeError:
                    html = asyncio.run(self._render(urls[0]))
                method = "playwright"
            except Exception as e:
                logger.warning("Playwright failed for Extreme E: %s", e)
        if not html:
            for url in urls:
                try:
                    resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"},
                                     timeout=15, follow_redirects=True)
                    if resp.status_code == 200:
                        html = resp.text
                        break
                except Exception:
                    pass
            if not html:
                html = ""  # May be fully dead
        return RawSeriesPayload(content=html, content_type="text/html", url=urls[0],
                                retrieved_at=datetime.utcnow(),
                                metadata={"series_id": series_id, "season": season, "method": method})

    async def _render(self, url):
        from browser_client import fetch_rendered_with_retry
        return (await fetch_rendered_with_retry(url)).content

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        season = raw.metadata.get("season", datetime.now().year)
        events = []
        soup = BeautifulSoup(raw.content, "html.parser")
        mm = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}

        containers = soup.find_all(["article","div","a","section"],
            class_=lambda c: c and any(k in c.lower() for k in ["event","race","round","calendar","card"]))
        for idx, c in enumerate(containers, 1):
            try:
                text = c.get_text(separator="\n", strip=True)
                if len(text) < 5: continue
                dm = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text, re.I)
                if not dm: continue
                g = dm.groups()
                sd,ed,mo = int(g[0]),int(g[1]),mm.get(g[2][:3].lower(),0)
                if not mo: continue
                lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip())>3 and not re.match(r"^\d",l.strip())]
                name = lines[0][:60] if lines else f"Extreme E Rd {idx}"
                tz, _ = infer_timezone_from_location(city=name, country="")
                events.append(Event(
                    event_id=f"extreme_e_{season}_r{idx}", series_id="extreme_e", name=name,
                    start_date=date(season,mo,sd), end_date=date(season,mo,ed),
                    venue=Venue(circuit=name, city=None, country="Unknown", timezone=tz or "UTC"),
                    sessions=[],
                    sources=[Source(url=raw.url, provider_name=self.name,
                                   retrieved_at=raw.retrieved_at, extraction_method=raw.metadata.get("method","http"))],
                ))
            except Exception as e:
                logger.debug("Extreme E %d: %s", idx, e)
        logger.info("Extreme E: %d events for %d", len(events), season)
        return events
