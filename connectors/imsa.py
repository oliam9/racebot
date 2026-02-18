"""
IMSA WeatherTech SportsCar Championship Connector.
Uses Playwright to render https://www.imsa.com/weathertech/schedule/
and capture API responses or parse the rendered DOM.
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


class IMSAConnector(Connector):
    """
    Connector for IMSA WeatherTech SportsCar Championship.
    Uses Playwright (site is behind Cloudflare).
    """

    BASE_URL = "https://www.imsa.com"
    SCHEDULE_URL = "https://www.imsa.com/weathertech/schedule/"

    @property
    def id(self) -> str:
        return "imsa_official"

    @property
    def name(self) -> str:
        return "IMSA WeatherTech Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="imsa",
                name="IMSA WeatherTech SportsCar Championship",
                category=SeriesCategory.ENDURANCE,
                connector_id=self.id,
            )
        ]

    # ── fetch ────────────────────────────────────────────────────────

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "imsa":
            raise ValueError(f"IMSA connector does not support: {series_id}")

        html = ""
        method = "http"

        # IMSA is behind Cloudflare — Playwright is required
        if self.playwright_enabled:
            try:
                html = self._fetch_with_playwright()
                method = "playwright"
            except Exception as e:
                logger.warning("Playwright failed for IMSA: %s", e)

        # Fallback: basic HTTP (will likely fail due to Cloudflare)
        if not html:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                }
                resp = httpx.get(self.SCHEDULE_URL, headers=headers, timeout=20, follow_redirects=True)
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.error("Failed to fetch IMSA schedule: %s", e)
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
            "january": 1, "february": 2, "march": 3, "april": 4,
            "june": 6, "july": 7, "august": 8, "september": 9,
            "october": 10, "november": 11, "december": 12,
        }

        # IMSA schedule typically has event cards/rows
        event_containers = soup.find_all(
            ["article", "div", "section", "li"],
            class_=lambda c: c and any(
                kw in c.lower() for kw in ["event", "race", "schedule", "round", "card"]
            ),
        )

        if not event_containers:
            # Broader: look for links to race detail pages
            event_containers = soup.find_all("a", href=re.compile(r"/race/|/event/|/schedule/"))

        for idx, container in enumerate(event_containers, 1):
            try:
                text = container.get_text(separator="\n", strip=True)
                if len(text) < 10:
                    continue

                # Parse date patterns
                # "Jan 24 - 26" or "January 24-26, 2026" or "24-26 Jan"
                date_match = re.search(
                    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2})\s*[-–]\s*(\d{1,2})",
                    text, re.IGNORECASE,
                )
                if not date_match:
                    date_match = re.search(
                        r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
                        text, re.IGNORECASE,
                    )

                if not date_match:
                    continue

                groups = date_match.groups()
                if groups[0].isdigit():
                    start_day, end_day = int(groups[0]), int(groups[1])
                    month_str = groups[2]
                else:
                    month_str = groups[0]
                    start_day, end_day = int(groups[1]), int(groups[2])

                month = month_map.get(month_str[:3].lower(), 0)
                if not month:
                    continue

                start_date = date(season, month, start_day)
                end_date = date(season, month, end_day)

                # Event name
                lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 3]
                event_name = f"IMSA Round {idx}"
                for line in lines:
                    # Skip date lines and short lines
                    if re.match(r"^\d", line) or len(line) < 5:
                        continue
                    if any(m in line.lower() for m in month_map.keys()):
                        continue
                    if len(line) < 60:
                        event_name = line
                        break

                # Track/venue detection
                track = event_name
                tz_name = "America/New_York"  # default to Eastern (most IMSA races)

                try:
                    tz_name_inferred, _ = infer_timezone_from_location(city=track, country="US")
                    if tz_name_inferred:
                        tz_name = tz_name_inferred
                except Exception:
                    pass

                events.append(
                    Event(
                        event_id=f"imsa_{season}_r{idx}",
                        series_id="imsa",
                        name=event_name,
                        start_date=start_date,
                        end_date=end_date,
                        venue=Venue(
                            circuit=track,
                            city=None,
                            country="US",
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
                logger.debug("Failed to parse IMSA event %d: %s", idx, e)

        logger.info("IMSA: extracted %d events for season %d", len(events), season)
        return events
