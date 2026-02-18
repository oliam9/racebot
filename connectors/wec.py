"""
FIA World Endurance Championship (WEC) Connector.
Uses Playwright to render https://www.fiawec.com/ and extract the calendar.
Falls back to the AI Scrapper pattern for session data.
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


class WECConnector(Connector):
    """
    Connector for FIA World Endurance Championship.
    Uses Playwright to render the fiawec.com calendar page
    and parse event data from the rendered DOM.
    """

    BASE_URL = "https://www.fiawec.com"
    CALENDAR_URL = "https://www.fiawec.com/en/season/calendar"

    @property
    def id(self) -> str:
        return "wec_official"

    @property
    def name(self) -> str:
        return "FIA WEC Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="wec",
                name="FIA World Endurance Championship",
                category=SeriesCategory.ENDURANCE,
                connector_id=self.id,
            )
        ]

    # ── fetch ────────────────────────────────────────────────────────

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "wec":
            raise ValueError(f"WEC connector does not support: {series_id}")

        html = ""
        method = "http"

        # Try Playwright first (site is JS-heavy)
        if self.playwright_enabled:
            try:
                html = self._fetch_with_playwright()
                method = "playwright"
            except Exception as e:
                logger.warning("Playwright failed for WEC: %s", e)

        # Fallback: basic HTTP
        if not html:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                }
                resp = httpx.get(self.CALENDAR_URL, headers=headers, timeout=15, follow_redirects=True)
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.error("Failed to fetch WEC calendar: %s", e)
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

        # Look for event cards/blocks in the page
        # WEC typically renders events in card-like containers
        event_containers = soup.find_all(
            ["article", "div", "section"],
            class_=lambda c: c and any(
                kw in c.lower() for kw in ["event", "race", "round", "calendar"]
            ),
        )

        if not event_containers:
            # Try looking for links to race detail pages
            event_containers = soup.find_all("a", href=re.compile(r"/race/|/event/|/round/"))

        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }

        for idx, container in enumerate(event_containers, 1):
            try:
                text = container.get_text(separator=" ", strip=True)

                # Skip if doesn't look like a race event
                if len(text) < 10:
                    continue

                # Try to extract a date pattern
                # Common: "14 Jun 2026" or "14-15 Jun" or "June 14-15, 2026"
                date_match = re.search(
                    r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
                    text, re.IGNORECASE,
                )
                if not date_match:
                    date_match = re.search(
                        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
                        text, re.IGNORECASE,
                    )

                if not date_match:
                    continue

                groups = date_match.groups()
                if len(groups) == 3:
                    start_day = int(groups[0])
                    end_day = int(groups[1])
                    month = month_map.get(groups[2][:3].lower(), 1)
                else:
                    start_day = int(groups[0])
                    end_day = start_day
                    month = month_map.get(groups[1][:3].lower(), 1)

                start_date = date(season, month, start_day)
                end_date = date(season, month, end_day)

                # Extract event name (usually circuit/location)
                # Remove the date portion and look for the main name
                name_text = text
                for pattern in [r"\d{1,2}\s*[-–]\s*\d{1,2}\s+\w+", r"\d{1,2}\s+\w+"]:
                    name_text = re.sub(pattern, "", name_text, count=1).strip()

                # Clean up
                name_parts = [p.strip() for p in name_text.split("\n") if p.strip() and len(p.strip()) > 2]
                event_name = name_parts[0] if name_parts else f"WEC Round {idx}"

                # Limit name length
                if len(event_name) > 60:
                    event_name = event_name[:57] + "..."

                # Try to get country/location
                country = ""
                tz_name = "UTC"
                try:
                    tz_name, _ = infer_timezone_from_location(city=event_name, country=country)
                    if not tz_name:
                        tz_name = "UTC"
                except Exception:
                    pass

                events.append(
                    Event(
                        event_id=f"wec_{season}_r{idx}",
                        series_id="wec",
                        name=event_name,
                        start_date=start_date,
                        end_date=end_date,
                        venue=Venue(
                            circuit=event_name,
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
                logger.debug("Failed to parse WEC event container %d: %s", idx, e)

        logger.info("WEC: extracted %d events for season %d", len(events), season)
        return events
