"""
Dakar Rally Connector.
Uses Playwright to render dakar.com.
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


class DakarConnector(Connector):
    """Connector for the Dakar Rally."""

    SCHEDULE_URL = "https://www.dakar.com/en/calendar"

    @property
    def id(self) -> str:
        return "dakar_official"

    @property
    def name(self) -> str:
        return "Dakar Rally Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [SeriesDescriptor(series_id="dakar", name="Dakar Rally",
                                 category=SeriesCategory.RALLY, connector_id=self.id)]

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "dakar":
            raise ValueError(f"Dakar connector does not support: {series_id}")
        html, method = "", "http"
        # Try multiple URLs: /en/calendar, /en/edition/YEAR, homepage
        urls = [
            f"https://www.dakar.com/en/edition/{season}",
            "https://www.dakar.com/en/calendar",
            "https://www.dakar.com/en/",
        ]
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
                logger.warning("Playwright failed for Dakar: %s", e)
        if not html:
            for url in urls:
                try:
                    resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"},
                                     timeout=15, follow_redirects=True)
                    if resp.status_code == 200 and len(resp.text) > 5000:
                        html = resp.text
                        break
                except Exception:
                    pass
            if not html:
                raise RuntimeError("Could not fetch Dakar calendar")
        return RawSeriesPayload(content=html, content_type="text/html", url=urls[0],
                                retrieved_at=datetime.utcnow(),
                                metadata={"series_id": series_id, "season": season, "method": method})

    async def _render(self, url):
        from browser_client import fetch_rendered_with_retry
        return (await fetch_rendered_with_retry(url)).content

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        season = raw.metadata.get("season", datetime.now().year)
        # Dakar is a single multi-week event (typically January)
        # Default: create one event for the whole rally
        events = []
        soup = BeautifulSoup(raw.content, "html.parser")

        # Try to find date range
        text = soup.get_text()
        dm = re.search(r"(\d{1,2})\s*(Jan|Feb)\w*\s*[-–to]+\s*(\d{1,2})\s*(Jan|Feb)\w*\s*(\d{4})?", text, re.I)
        mm = {"jan":1,"feb":2}
        if dm:
            g = dm.groups()
            sd, sm = int(g[0]), mm.get(g[1][:3].lower(), 1)
            ed, em = int(g[2]), mm.get(g[3][:3].lower(), 1)
            yr = int(g[4]) if g[4] else season
            start_date = date(yr, sm, sd)
            end_date = date(yr, em, ed)
        else:
            # Default: Dakar typically runs early January
            start_date = date(season, 1, 3)
            end_date = date(season, 1, 17)

        events.append(Event(
            event_id=f"dakar_{season}", series_id="dakar",
            name=f"Dakar Rally {season}",
            start_date=start_date, end_date=end_date,
            venue=Venue(circuit="Dakar Rally", city=None, country="Saudi Arabia", timezone="Asia/Riyadh"),
            sessions=[],
            sources=[Source(url=raw.url, provider_name=self.name,
                           retrieved_at=raw.retrieved_at, extraction_method=raw.metadata.get("method","http"))],
        ))
        logger.info("Dakar: %d events for %d", len(events), season)
        return events
