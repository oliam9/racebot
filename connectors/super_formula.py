"""
Super Formula Championship Connector.
Uses Playwright to render superformula.net and extract race calendar.
"""
from datetime import datetime, date
from typing import List, Optional
import httpx
import re
import logging
import asyncio
from bs4 import BeautifulSoup

from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SeriesCategory, SessionType, SessionStatus
from .base import Connector, RawSeriesPayload
from validators.timezone_utils import infer_timezone_from_location

logger = logging.getLogger(__name__)


class SuperFormulaConnector(Connector):
    """Connector for Super Formula Championship (Japan)."""

    BASE_URL = "https://www.superformula.net"
    SCHEDULE_URL = "https://www.superformula.net/sf2/en/race/"

    @property
    def id(self) -> str:
        return "super_formula_official"

    @property
    def name(self) -> str:
        return "Super Formula Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="super_formula",
                name="Super Formula Championship",
                category=SeriesCategory.OPENWHEEL,
                connector_id=self.id,
            )
        ]

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "super_formula":
            raise ValueError(f"Super Formula connector does not support: {series_id}")

        html = ""
        method = "http"

        if self.playwright_enabled:
            try:
                html = self._pw_fetch()
                method = "playwright"
            except Exception as e:
                logger.warning("Playwright failed for Super Formula: %s", e)

        if not html:
            try:
                resp = httpx.get(
                    self.SCHEDULE_URL,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=15, follow_redirects=True, verify=False,
                )
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.error("Failed to fetch Super Formula: %s", e)
                raise

        return RawSeriesPayload(
            content=html, content_type="text/html", url=self.SCHEDULE_URL,
            retrieved_at=datetime.utcnow(),
            metadata={"series_id": series_id, "season": season, "method": method},
        )

    def _pw_fetch(self) -> str:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as ex:
                    return ex.submit(asyncio.run, self._render()).result(timeout=60)
            return loop.run_until_complete(self._render())
        except RuntimeError:
            return asyncio.run(self._render())

    async def _render(self) -> str:
        from browser_client import fetch_rendered_with_retry
        r = await fetch_rendered_with_retry(self.SCHEDULE_URL)
        return r.content

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        season = raw.metadata.get("season", datetime.now().year)
        events: List[Event] = []
        soup = BeautifulSoup(raw.content, "html.parser")

        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }

        containers = soup.find_all(
            ["article", "div", "a", "li"],
            class_=lambda c: c and any(kw in c.lower() for kw in ["race", "event", "round", "schedule", "card"]),
        )

        for idx, c in enumerate(containers, 1):
            try:
                text = c.get_text(separator="\n", strip=True)
                if len(text) < 5:
                    continue

                dm = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text, re.I)
                if not dm:
                    dm = re.search(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", text, re.I)
                if not dm:
                    continue

                g = dm.groups()
                if len(g) == 3:
                    sd, ed = int(g[0]), int(g[1])
                    mo = month_map.get(g[2][:3].lower(), 0)
                else:
                    sd = ed = int(g[0])
                    mo = month_map.get(g[1][:3].lower(), 0)
                if not mo:
                    continue

                lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 3 and not re.match(r"^\d", l.strip())]
                name = lines[0] if lines else f"Super Formula Rd {idx}"
                if len(name) > 60:
                    name = name[:57] + "..."

                events.append(Event(
                    event_id=f"sf_{season}_r{idx}", series_id="super_formula",
                    name=name, start_date=date(season, mo, sd), end_date=date(season, mo, ed),
                    venue=Venue(circuit=name, city=None, country="Japan", timezone="Asia/Tokyo"),
                    sessions=[],
                    sources=[Source(url=raw.url, provider_name=self.name,
                                   retrieved_at=raw.retrieved_at,
                                   extraction_method=raw.metadata.get("method", "http"))],
                ))
            except Exception as e:
                logger.debug("Super Formula event %d: %s", idx, e)

        logger.info("Super Formula: %d events for %d", len(events), season)
        return events
