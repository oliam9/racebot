"""
AMA Supercross Championship Connector.
Uses Playwright to render supercrosslive.com/schedule.
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

logger = logging.getLogger(__name__)


class AMASupercrossConnector(Connector):
    """Connector for AMA Supercross Championship."""

    SCHEDULE_URL = "https://www.supercrosslive.com/schedule"

    @property
    def id(self) -> str:
        return "ama_supercross_official"

    @property
    def name(self) -> str:
        return "AMA Supercross Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [SeriesDescriptor(series_id="ama_supercross", name="AMA Supercross Championship",
                                 category=SeriesCategory.MOTORCYCLE, connector_id=self.id)]

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "ama_supercross":
            raise ValueError(f"AMA Supercross connector does not support: {series_id}")
        html, method = "", "http"
        urls = [self.SCHEDULE_URL, "https://www.supercrosslive.com/"]
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
                logger.warning("Playwright failed for Supercross: %s", e)
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
                html = ""
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

        containers = soup.find_all(["article","div","a","section","li","tr"],
            class_=lambda c: c and any(k in c.lower() for k in ["event","race","round","schedule","card"]))
        if not containers:
            containers = soup.find_all("a", href=re.compile(r"/event/|/race/|/round/"))

        for idx, c in enumerate(containers, 1):
            try:
                text = c.get_text(separator="\n", strip=True)
                if len(text) < 5: continue
                # US date format: "Jan 4" or "January 4" or "1/4/2026"
                dm = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2})", text, re.I)
                if not dm: continue
                mo = mm.get(dm.group(1)[:3].lower(), 0)
                day = int(dm.group(2))
                if not mo: continue
                lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip())>3 and not re.match(r"^\d",l.strip())]
                # Filter out month lines
                name_lines = [l for l in lines if not any(m in l.lower() for m in mm.keys())]
                name = name_lines[0][:60] if name_lines else f"Supercross Rd {idx}"
                events.append(Event(
                    event_id=f"sx_{season}_r{idx}", series_id="ama_supercross", name=name,
                    start_date=date(season,mo,day), end_date=date(season,mo,day),
                    venue=Venue(circuit=name, city=None, country="US", timezone="America/New_York"),
                    sessions=[],
                    sources=[Source(url=raw.url, provider_name=self.name,
                                   retrieved_at=raw.retrieved_at, extraction_method=raw.metadata.get("method","http"))],
                ))
            except Exception as e:
                logger.debug("Supercross %d: %s", idx, e)
        logger.info("AMA Supercross: %d events for %d", len(events), season)
        return events
