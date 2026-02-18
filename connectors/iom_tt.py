"""
Isle of Man TT Connector.
Uses Playwright (site behind Cloudflare).
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


class IsleOfManTTConnector(Connector):
    """Connector for the Isle of Man TT. Single annual event."""

    SCHEDULE_URL = "https://www.iomtt.com/races/schedule"

    @property
    def id(self) -> str:
        return "iom_tt_official"

    @property
    def name(self) -> str:
        return "Isle of Man TT Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [SeriesDescriptor(series_id="iom_tt", name="Isle of Man TT",
                                 category=SeriesCategory.MOTORCYCLE, connector_id=self.id)]

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "iom_tt":
            raise ValueError(f"IoM TT connector does not support: {series_id}")
        html, method = "", "http"
        # Site is Cloudflare-protected — Playwright strongly preferred
        if self.playwright_enabled:
            try:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as ex:
                            html = ex.submit(asyncio.run, self._render()).result(timeout=60)
                    else:
                        html = loop.run_until_complete(self._render())
                except RuntimeError:
                    html = asyncio.run(self._render())
                method = "playwright"
            except Exception as e:
                logger.warning("Playwright failed for IoM TT: %s", e)
        if not html:
            try:
                resp = httpx.get(self.SCHEDULE_URL, headers={"User-Agent": "Mozilla/5.0"},
                                 timeout=15, follow_redirects=True)
                html = resp.text
            except Exception as e:
                logger.warning("HTTP failed for IoM TT: %s", e)
                html = ""
        return RawSeriesPayload(content=html, content_type="text/html", url=self.SCHEDULE_URL,
                                retrieved_at=datetime.utcnow(),
                                metadata={"series_id": series_id, "season": season, "method": method})

    async def _render(self):
        from browser_client import fetch_rendered_with_retry
        return (await fetch_rendered_with_retry(self.SCHEDULE_URL)).content

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        season = raw.metadata.get("season", datetime.now().year)
        events = []
        soup = BeautifulSoup(raw.content, "html.parser")

        # Try to find TT dates from the page
        text = soup.get_text()
        mm = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
        dm = re.search(r"(\d{1,2})\s*(May|Jun|Jul)\w*\s*[-–to]+\s*(\d{1,2})\s*(May|Jun|Jul)", text, re.I)

        if dm:
            g = dm.groups()
            sd, sm = int(g[0]), mm.get(g[1][:3].lower(), 6)
            ed, em = int(g[2]), mm.get(g[3][:3].lower(), 6)
            start_date = date(season, sm, sd)
            end_date = date(season, em, ed)
        else:
            # TT typically runs late May – early June
            start_date = date(season, 5, 24)
            end_date = date(season, 6, 7)

        # Single event: the TT fortnight
        events.append(Event(
            event_id=f"iomtt_{season}", series_id="iom_tt",
            name=f"Isle of Man TT {season}",
            start_date=start_date, end_date=end_date,
            venue=Venue(circuit="Snaefell Mountain Course", city="Douglas",
                       country="Isle of Man", timezone="Europe/Isle_of_Man"),
            sessions=[],
            sources=[Source(url=raw.url, provider_name=self.name,
                           retrieved_at=raw.retrieved_at, extraction_method=raw.metadata.get("method","http"))],
        ))
        logger.info("IoM TT: %d events for %d", len(events), season)
        return events
