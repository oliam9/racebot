"""
Stock Car Pro Series (Brazil) Connector.
Uses Playwright to render stockcar.com.br/calendario.
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

# Brazilian month names
_BR_MONTHS = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
    # English fallback
    "feb": 2, "apr": 4, "may": 5, "aug": 8, "sep": 9, "oct": 10, "dec": 12,
}


class StockCarBRConnector(Connector):
    """Connector for Stock Car Pro Series (Brazil)."""

    SCHEDULE_URL = "https://www.stockcar.com.br/calendario"

    @property
    def id(self) -> str:
        return "stock_car_br_official"

    @property
    def name(self) -> str:
        return "Stock Car Pro Series Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [SeriesDescriptor(series_id="stock_car_br", name="Stock Car Pro Series",
                                 category=SeriesCategory.TOURING, connector_id=self.id)]

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "stock_car_br":
            raise ValueError(f"Stock Car BR connector does not support: {series_id}")
        html, method = "", "http"
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
                logger.warning("Playwright failed for Stock Car BR: %s", e)
        if not html:
            try:
                resp = httpx.get(self.SCHEDULE_URL, headers={"User-Agent": "Mozilla/5.0"},
                                 timeout=15, follow_redirects=True)
                html = resp.text
            except Exception as e:
                logger.error("Failed to fetch Stock Car BR: %s", e)
                raise
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

        containers = soup.find_all(["article","div","a","section","li"],
            class_=lambda c: c and any(k in c.lower() for k in ["event","race","round","etapa","calendar","card"]))
        if not containers:
            containers = soup.find_all("a", href=re.compile(r"/etapa/|/race/|/event/"))

        for idx, c in enumerate(containers, 1):
            try:
                text = c.get_text(separator="\n", strip=True)
                if len(text) < 5: continue
                # Try Portuguese month names first, then English
                dm = re.search(r"(\d{1,2})\s*[-–a]\s*(\d{1,2})\s+(Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez|Feb|Apr|May|Aug|Sep|Oct|Dec)", text, re.I)
                if not dm:
                    dm = re.search(r"(\d{1,2})\s+(Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez|Feb|Apr|May|Aug|Sep|Oct|Dec)", text, re.I)
                if not dm: continue
                g = dm.groups()
                if len(g)==3: sd,ed,mo = int(g[0]),int(g[1]),_BR_MONTHS.get(g[2][:3].lower(),0)
                else: sd,ed,mo = int(g[0]),int(g[0]),_BR_MONTHS.get(g[1][:3].lower(),0)
                if not mo: continue
                lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip())>3 and not re.match(r"^\d",l.strip())]
                name = lines[0][:60] if lines else f"Stock Car Etapa {idx}"
                events.append(Event(
                    event_id=f"scbr_{season}_r{idx}", series_id="stock_car_br", name=name,
                    start_date=date(season,mo,sd), end_date=date(season,mo,ed),
                    venue=Venue(circuit=name, city=None, country="Brazil", timezone="America/Sao_Paulo"),
                    sessions=[],
                    sources=[Source(url=raw.url, provider_name=self.name,
                                   retrieved_at=raw.retrieved_at, extraction_method=raw.metadata.get("method","http"))],
                ))
            except Exception as e:
                logger.debug("Stock Car BR %d: %s", idx, e)
        logger.info("Stock Car BR: %d events for %d", len(events), season)
        return events
