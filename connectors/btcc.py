"""
British Touring Car Championship (BTCC) Connector.
Uses Playwright to render https://www.btcc.net/calendar/ and parse events.
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

# BTCC circuits (all in the UK)
_BTCC_CIRCUITS = {
    "brands hatch": {"city": "Longfield", "tz": "Europe/London"},
    "donington": {"city": "Castle Donington", "tz": "Europe/London"},
    "donington park": {"city": "Castle Donington", "tz": "Europe/London"},
    "silverstone": {"city": "Silverstone", "tz": "Europe/London"},
    "thruxton": {"city": "Andover", "tz": "Europe/London"},
    "oulton park": {"city": "Tarporley", "tz": "Europe/London"},
    "croft": {"city": "Dalton-on-Tees", "tz": "Europe/London"},
    "snetterton": {"city": "Norwich", "tz": "Europe/London"},
    "knockhill": {"city": "Dunfermline", "tz": "Europe/London"},
}


class BTCCConnector(Connector):
    """
    Connector for the British Touring Car Championship.
    Uses Playwright to render the BTCC calendar page (JS-heavy).
    """

    BASE_URL = "https://www.btcc.net"
    CALENDAR_URL = "https://www.btcc.net/calendar/"

    @property
    def id(self) -> str:
        return "btcc_official"

    @property
    def name(self) -> str:
        return "BTCC Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="btcc",
                name="British Touring Car Championship",
                category=SeriesCategory.TOURING,
                connector_id=self.id,
            )
        ]

    # ── fetch ────────────────────────────────────────────────────────

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "btcc":
            raise ValueError(f"BTCC connector does not support: {series_id}")

        html = ""
        method = "http"

        if self.playwright_enabled:
            try:
                html = self._fetch_with_playwright()
                method = "playwright"
            except Exception as e:
                logger.warning("Playwright failed for BTCC: %s", e)

        if not html:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                }
                resp = httpx.get(self.CALENDAR_URL, headers=headers, timeout=15, follow_redirects=True)
                resp.raise_for_status()
                html = resp.text
            except Exception as e:
                logger.error("Failed to fetch BTCC calendar: %s", e)
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

        # BTCC calendar — search for containers with event-like classes
        containers = soup.find_all(
            ["article", "div", "section", "a", "tr", "li"],
            class_=lambda c: c and any(
                kw in c.lower() for kw in ["event", "race", "round", "calendar", "card", "fixture"]
            ),
        )

        if not containers:
            # Fallback: look for links referencing events
            containers = soup.find_all("a", href=re.compile(r"/event/|/round/|/race/"))

        for idx, container in enumerate(containers, 1):
            try:
                text = container.get_text(separator="\n", strip=True)
                if len(text) < 5:
                    continue

                # Date patterns: "19 - 20 Apr" or "19-20 April"
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
                    start_day, end_day = int(groups[0]), int(groups[1])
                    month = month_map.get(groups[2][:3].lower(), 0)
                else:
                    start_day = end_day = int(groups[0])
                    month = month_map.get(groups[1][:3].lower(), 0)

                if not month:
                    continue

                start_date = date(season, month, start_day)
                end_date = date(season, month, end_day)

                # Detect circuit name from text
                circuit_name = "TBD"
                city = None
                for circuit_key, info in _BTCC_CIRCUITS.items():
                    if circuit_key in text.lower():
                        circuit_name = circuit_key.title()
                        city = info["city"]
                        break

                # If no known circuit, use first meaningful line as name
                if circuit_name == "TBD":
                    lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 3]
                    for line in lines:
                        if re.match(r"^\d", line) or len(line) < 5:
                            continue
                        if any(m in line.lower() for m in month_map.keys()):
                            continue
                        if len(line) < 50:
                            circuit_name = line
                            break

                event_name = f"BTCC {circuit_name}"

                events.append(
                    Event(
                        event_id=f"btcc_{season}_r{idx}",
                        series_id="btcc",
                        name=event_name,
                        start_date=start_date,
                        end_date=end_date,
                        venue=Venue(
                            circuit=circuit_name,
                            city=city,
                            country="United Kingdom",
                            timezone="Europe/London",
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
                logger.debug("Failed to parse BTCC event %d: %s", idx, e)

        logger.info("BTCC: extracted %d events for season %d", len(events), season)
        return events
