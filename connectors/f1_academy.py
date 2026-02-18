"""
F1 Academy Connector.
Uses __NEXT_DATA__ from f1academy.com — same platform as FIA F2 / F3.
"""
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import httpx
import json
import re
import logging
from dateutil import parser as date_parser
from bs4 import BeautifulSoup

from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SeriesCategory, SessionType, SessionStatus
from .base import Connector, RawSeriesPayload
from validators.timezone_utils import infer_timezone_from_location

logger = logging.getLogger(__name__)


class F1AcademyConnector(Connector):
    """
    Connector for F1 Academy.
    Uses __NEXT_DATA__ extraction (same FIA website platform as F2/F3).
    """

    BASE_URL = "https://www.f1academy.com"
    CALENDAR_URL = "https://www.f1academy.com/Calendar"

    @property
    def id(self) -> str:
        return "f1_academy_official"

    @property
    def name(self) -> str:
        return "F1 Academy Official"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="f1_academy",
                name="F1 Academy",
                category=SeriesCategory.OPENWHEEL,
                connector_id=self.id,
            )
        ]

    # ── fetch ────────────────────────────────────────────────────────

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "f1_academy":
            raise ValueError(f"F1 Academy connector does not support: {series_id}")

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }

        # F1 Academy may use different URL paths depending on the year
        urls_to_try = [
            f"{self.BASE_URL}/Calendar",
            f"{self.BASE_URL}/Racing/{season}",
            f"{self.BASE_URL}/Schedule",
            f"{self.BASE_URL}/",
        ]

        for url in urls_to_try:
            try:
                resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
                if resp.status_code == 200 and "__NEXT_DATA__" in resp.text:
                    # Check if pageProps has actual data (not a 404 page)
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")
                    tag = soup.find("script", id="__NEXT_DATA__")
                    if tag and tag.string:
                        import json as _json
                        data = _json.loads(tag.string)
                        pp = data.get("props", {}).get("pageProps", {})
                        if pp.get("statusCode") == 404:
                            logger.debug("F1 Academy %s returned 404 in pageProps", url)
                            continue
                    return RawSeriesPayload(
                        content=resp.text,
                        content_type="text/html",
                        url=url,
                        retrieved_at=datetime.utcnow(),
                        metadata={"series_id": series_id, "season": season},
                    )
            except Exception as e:
                logger.debug("F1 Academy URL %s failed: %s", url, e)

        # If all URLs failed, return the homepage content (may have limited data)
        logger.warning("F1 Academy: no calendar page found for %d, using homepage", season)
        resp = httpx.get(self.BASE_URL, headers=headers, timeout=15, follow_redirects=True)
        return RawSeriesPayload(
            content=resp.text,
            content_type="text/html",
            url=self.BASE_URL,
            retrieved_at=datetime.utcnow(),
            metadata={"series_id": series_id, "season": season},
        )

    # ── extract ──────────────────────────────────────────────────────

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        season = raw.metadata.get("season", datetime.now().year)
        series_id = raw.metadata.get("series_id", "f1_academy")

        try:
            soup = BeautifulSoup(raw.content, "html.parser")
            next_data = soup.find("script", id="__NEXT_DATA__")

            if not next_data or not next_data.string:
                logger.warning("No __NEXT_DATA__ found on F1 Academy page")
                return []

            data = json.loads(next_data.string)
            page_data = data.get("props", {}).get("pageProps", {}).get("pageData", {})
            races = page_data.get("Races", [])

            # Also try seasonData (like F2/F3 pattern)
            if not races:
                season_data = data.get("props", {}).get("pageProps", {}).get("seasonData", [])
                races = season_data if isinstance(season_data, list) else []

            if not races:
                logger.warning("No races found in F1 Academy __NEXT_DATA__")
                return []

            logger.info("F1 Academy: found %d races in __NEXT_DATA__", len(races))

            events: List[Event] = []
            for item in races:
                evt = self._parse_nextjs_event(item, series_id, season, raw.url)
                if evt:
                    events.append(evt)
            return events

        except Exception as e:
            logger.error("Failed to parse F1 Academy data: %s", e)
            return []

    def _parse_nextjs_event(self, item: Dict, series_id: str, season: int,
                            source_url: str) -> Optional[Event]:
        """Parse a single event from the __NEXT_DATA__ structure.
        Same format as F2/F3:
        {
          "RaceId": ..., "RoundNumber": ...,
          "RaceStartDate": "2026-...", "RaceEndDate": "2026-...",
          "CircuitShortName": "...", "CircuitName": "...",
          "CountryName": "...",
          "Sessions": [...]
        }
        """
        round_num = item.get("RoundNumber")
        if not round_num:
            return None

        name = item.get("CircuitShortName", item.get("CountryName", "Unknown"))
        event_id = f"f1a_{season}_r{round_num}"

        # Dates
        try:
            start_date = date_parser.parse(item["RaceStartDate"]).date()
            end_str = item.get("RaceEndDate")
            end_date = date_parser.parse(end_str).date() if end_str else start_date
        except (ValueError, TypeError, KeyError):
            logger.warning("Invalid dates for F1 Academy event %s", name)
            return None

        # Venue
        city = item.get("CircuitShortName", "")
        country = item.get("CountryName", "Unknown")
        circuit = item.get("CircuitName", city)

        tz_name, tz_inferred = infer_timezone_from_location(country, city)
        if not tz_name:
            tz_name = "UTC"

        # Sessions
        sessions: List[Session] = []
        for sess_item in item.get("Sessions", []):
            session = self._parse_session(sess_item, event_id)
            if session:
                sessions.append(session)

        return Event(
            event_id=event_id,
            series_id=series_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            venue=Venue(
                circuit=circuit,
                city=city or None,
                country=country,
                timezone=tz_name,
                inferred_timezone=tz_inferred if tz_name != "UTC" else True,
            ),
            sessions=sessions,
            sources=[
                Source(
                    url=source_url,
                    provider_name=self.name,
                    retrieved_at=datetime.utcnow(),
                    extraction_method="nextjs_html",
                )
            ],
        )

    @staticmethod
    def _parse_session(sess: Dict, event_id: str) -> Optional[Session]:
        """Parse a session from __NEXT_DATA__ Session object."""
        s_code = (sess.get("SessionCode") or "").upper()
        s_short = (sess.get("SessionShortName") or "").upper()
        s_name = sess.get("SessionName", "")

        if not s_name:
            return None

        # Type mapping (same as F2)
        if "QUAL" in s_code or "QUAL" in s_short:
            stype = SessionType.QUALIFYING
        elif "RACE" in s_code or "RESULT" in s_code:
            if "SR" in s_short or "SPRINT" in s_name.upper():
                stype = SessionType.SPRINT
            else:
                stype = SessionType.RACE
        elif "PRACTICE" in s_code:
            stype = SessionType.PRACTICE
        else:
            stype = SessionType.PRACTICE

        # Times
        start = None
        end = None
        if sess.get("SessionStartTime"):
            try:
                start = date_parser.parse(sess["SessionStartTime"]).isoformat()
            except Exception:
                pass
        if sess.get("SessionEndTime"):
            try:
                end = date_parser.parse(sess["SessionEndTime"]).isoformat()
            except Exception:
                pass

        session_id = f"{event_id}_{s_short.replace(' ', '').lower()}_{sess.get('SessionId', '')}"

        return Session(
            session_id=session_id,
            type=stype,
            name=s_name,
            start=start,
            end=end or "TBC",
            status=SessionStatus.SCHEDULED,
        )
