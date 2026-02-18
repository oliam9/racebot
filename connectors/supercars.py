"""
Supercars Championship (Australia) Connector.
Uses Playwright to render https://www.supercars.com/schedule/ and parse events.
"""
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
import json
import re
import logging
import asyncio
from dateutil import parser as date_parser
from bs4 import BeautifulSoup

from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SeriesCategory, SessionType, SessionStatus
from .base import Connector, RawSeriesPayload
from validators.timezone_utils import infer_timezone_from_location

logger = logging.getLogger(__name__)

# Australian circuits and their timezones
_AU_TRACK_TZ = {
    "adelaide": "Australia/Adelaide",
    "albert park": "Australia/Melbourne",
    "bathurst": "Australia/Sydney",
    "darwin": "Australia/Darwin",
    "gold coast": "Australia/Brisbane",
    "surfers paradise": "Australia/Brisbane",
    "phillip island": "Australia/Melbourne",
    "sandown": "Australia/Melbourne",
    "sydney": "Australia/Sydney",
    "sydney motorsport park": "Australia/Sydney",
    "perth": "Australia/Perth",
    "wanneroo": "Australia/Perth",
    "townsville": "Australia/Brisbane",
    "winton": "Australia/Melbourne",
    "tailem bend": "Australia/Adelaide",
    "the bend": "Australia/Adelaide",
    "pukekohe": "Pacific/Auckland",
    "taupo": "Pacific/Auckland",
    "hampton downs": "Pacific/Auckland",
    "auckland": "Pacific/Auckland",
}


class SupercarsConnector(Connector):
    """
    Connector for the Supercars Championship (Australia).
    Uses Playwright to render the schedule page.
    """

    BASE_URL = "https://www.supercars.com"
    SCHEDULE_URL = "https://www.supercars.com/schedule/"

    @property
    def id(self) -> str:
        return "supercars_official"

    @property
    def name(self) -> str:
        return "Supercars Championship Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="supercars",
                name="Supercars Championship",
                category=SeriesCategory.TOURING,
                connector_id=self.id,
            )
        ]

    # ── fetch ────────────────────────────────────────────────────────

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "supercars":
            raise ValueError(f"Supercars connector does not support: {series_id}")

        html = ""
        method = "http"

        if self.playwright_enabled:
            try:
                html = self._fetch_with_playwright()
                method = "playwright"
            except Exception as e:
                logger.warning("Playwright failed for Supercars: %s", e)

        if not html:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                }
                resp = httpx.get(self.SCHEDULE_URL, headers=headers, timeout=15, follow_redirects=True)
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.error("Failed to fetch Supercars schedule: %s", e)
                raise

        return RawSeriesPayload(
            content=html,
            content_type="text/html",
            url=self.SCHEDULE_URL,
            retrieved_at=datetime.utcnow(),
            metadata={"series_id": series_id, "season": season, "method": method},
        )

    def _fetch_with_playwright(self) -> str:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._pw_render())
                    return future.result(timeout=60)
            else:
                return loop.run_until_complete(self._pw_render())
        except RuntimeError:
            return asyncio.run(self._pw_render())

    async def _pw_render(self) -> str:
        from browser_client import fetch_rendered_with_retry
        rendered = await fetch_rendered_with_retry(self.SCHEDULE_URL)
        return rendered.content

    # ── extract ──────────────────────────────────────────────────────

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        season = raw.metadata.get("season", datetime.now().year)
        return self._parse_html(raw.content, season, raw)

    def _parse_html(self, html: str, season: int, raw: RawSeriesPayload) -> List[Event]:
        events: List[Event] = []
        soup = BeautifulSoup(html, "html.parser")

        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }

        # Look for event containers
        containers = soup.find_all(
            ["article", "div", "section", "a", "li"],
            class_=lambda c: c and any(
                kw in c.lower() for kw in ["event", "race", "round", "schedule", "card"]
            ),
        )

        if not containers:
            containers = soup.find_all("a", href=re.compile(r"/event/|/round/"))

        for idx, container in enumerate(containers, 1):
            try:
                text = container.get_text(separator="\n", strip=True)
                if len(text) < 8:
                    continue

                # Date patterns: "7-9 Feb" or "Feb 7 - 9" or "7 - 9 February"
                date_match = re.search(
                    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
                    text, re.IGNORECASE,
                )
                if not date_match:
                    date_match = re.search(
                        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2})\s*[-–]\s*(\d{1,2})",
                        text, re.IGNORECASE,
                    )

                if not date_match:
                    continue

                groups = date_match.groups()
                if groups[0].isdigit():
                    start_day, end_day = int(groups[0]), int(groups[1])
                    month = month_map.get(groups[2][:3].lower(), 0)
                else:
                    month = month_map.get(groups[0][:3].lower(), 0)
                    start_day, end_day = int(groups[1]), int(groups[2])

                if not month:
                    continue

                start_date = date(season, month, start_day)
                end_date = date(season, month, end_day)

                # Event name
                lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 3]
                event_name = f"Supercars Round {idx}"
                for line in lines:
                    if re.match(r"^\d", line) or len(line) < 5:
                        continue
                    if any(m in line.lower() for m in month_map.keys()):
                        continue
                    if len(line) < 60:
                        event_name = line
                        break

                # Timezone from track name
                tz_name = "Australia/Sydney"
                for track_key, tz in _AU_TRACK_TZ.items():
                    if track_key in event_name.lower() or track_key in text.lower():
                        tz_name = tz
                        break

                events.append(
                    Event(
                        event_id=f"supercars_{season}_r{idx}",
                        series_id="supercars",
                        name=event_name,
                        start_date=start_date,
                        end_date=end_date,
                        venue=Venue(
                            circuit=event_name,
                            city=None,
                            country="Australia",
                            timezone=tz_name,
                        ),
                        sessions=[],
                        sources=[
                            Source(
                                url=raw.url,
                                provider_name=self.name,
                                retrieved_at=raw.retrieved_at,
                                extraction_method=raw.metadata.get("method", "http"),
                            )
                        ],
                    )
                )

            except Exception as e:
                logger.debug("Failed to parse Supercars event %d: %s", idx, e)

        logger.info("Supercars: extracted %d events for season %d", len(events), season)
        return events
