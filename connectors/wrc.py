"""
FIA World Rally Championship (WRC) Connector.
Uses Playwright to render https://www.wrc.com/en/calendar/ and extract calendar data.
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


class WRCConnector(Connector):
    """
    Connector for FIA World Rally Championship.
    WRC.com is a SPA that loads data via internal APIs.
    Uses Playwright to render the page and parse the DOM.
    """

    BASE_URL = "https://www.wrc.com"
    CALENDAR_URL = "https://www.wrc.com/en/calendar/"

    @property
    def id(self) -> str:
        return "wrc_official"

    @property
    def name(self) -> str:
        return "FIA WRC Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="wrc",
                name="FIA World Rally Championship",
                category=SeriesCategory.RALLY,
                connector_id=self.id,
            )
        ]

    # ── fetch ────────────────────────────────────────────────────────

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "wrc":
            raise ValueError(f"WRC connector does not support: {series_id}")

        html = ""
        method = "http"

        # Playwright is strongly preferred for WRC (it's a SPA)
        if self.playwright_enabled:
            try:
                html = self._fetch_with_playwright()
                method = "playwright"
            except Exception as e:
                logger.warning("Playwright failed for WRC: %s", e)

        # Fallback: basic HTTP (limited data from the SPA)
        if not html:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                }
                resp = httpx.get(self.CALENDAR_URL, headers=headers, timeout=20, follow_redirects=True)
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.error("Failed to fetch WRC calendar: %s", e)
                raise

        return RawSeriesPayload(
            content=html,
            content_type="text/html",
            url=self.CALENDAR_URL,
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
        rendered = await fetch_rendered_with_retry(self.CALENDAR_URL)
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

        # WRC calendar shows rally events as cards
        # Look for event containers
        event_containers = soup.find_all(
            ["article", "div", "a", "section"],
            class_=lambda c: c and any(
                kw in c.lower() for kw in ["event", "rally", "round", "calendar-item", "card"]
            ),
        )

        if not event_containers:
            # Broad search: look for date + rally name patterns
            event_containers = soup.find_all(
                "a", href=re.compile(r"/rally/|/event/|/championship/")
            )

        for idx, container in enumerate(event_containers, 1):
            try:
                text = container.get_text(separator="\n", strip=True)
                if len(text) < 5:
                    continue

                # Parse date range: "23 - 26 Jan" or "23-26 January"
                date_match = re.search(
                    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
                    text, re.IGNORECASE,
                )
                if not date_match:
                    # Single date: "23 Jan"
                    date_match = re.search(
                        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
                        text, re.IGNORECASE,
                    )

                if not date_match:
                    continue

                groups = date_match.groups()
                if len(groups) == 3:
                    start_day, end_day = int(groups[0]), int(groups[1])
                    month = month_map.get(groups[2][:3].lower(), 1)
                else:
                    start_day = end_day = int(groups[0])
                    month = month_map.get(groups[1][:3].lower(), 1)

                start_date = date(season, month, start_day)
                end_date = date(season, month, end_day)

                # Extract rally name
                lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 2]
                # Find the line that looks like a rally name (not a date, not a number)
                rally_name = f"WRC Round {idx}"
                for line in lines:
                    if not re.match(r"^\d", line) and "rally" in line.lower():
                        rally_name = line
                        break
                    if not re.match(r"^\d", line) and len(line) > 5 and len(line) < 50:
                        rally_name = line
                        # Don't break — keep looking for better "Rally" matches

                # Country detection
                country = ""
                for line in lines:
                    line_l = line.lower()
                    for c in ["monte carlo", "sweden", "kenya", "croatia", "portugal",
                              "italy", "finland", "greece", "chile", "japan",
                              "germany", "spain", "uk", "wales", "turkey", "mexico",
                              "estonia", "new zealand", "australia", "belgium"]:
                        if c in line_l:
                            country = c.title()
                            break

                tz_name = "UTC"
                try:
                    tz_name, _ = infer_timezone_from_location(city=rally_name, country=country)
                    if not tz_name:
                        tz_name = "UTC"
                except Exception:
                    pass

                events.append(
                    Event(
                        event_id=f"wrc_{season}_r{idx}",
                        series_id="wrc",
                        name=rally_name,
                        start_date=start_date,
                        end_date=end_date,
                        venue=Venue(
                            circuit=rally_name,
                            city=None,
                            country=country or "Unknown",
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
                logger.debug("Failed to parse WRC event %d: %s", idx, e)

        logger.info("WRC: extracted %d events for season %d", len(events), season)
        return events
