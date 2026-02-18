"""
NASCAR Cup Series Connector using the official NASCAR CDN API.
API: https://cf.nascar.com/cacher/{year}/{series_id}/race_list_basic.json

Series IDs: 1 = Cup, 2 = Xfinity, 3 = Craftsman Truck
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
import httpx
import json
import logging
from dateutil import parser as date_parser

from models.schema import Event, Session, Venue, Source, SeriesDescriptor
from models.enums import SeriesCategory, SessionType, SessionStatus
from .base import Connector, RawSeriesPayload
from validators.timezone_utils import infer_timezone_from_location

logger = logging.getLogger(__name__)

# NASCAR schedule items use run_type to distinguish sessions:
#   0 = logistics/admin, 1 = Practice, 2 = Qualifying, 3 = Race
_RUN_TYPE_MAP = {
    1: (SessionType.PRACTICE, "Practice"),
    2: (SessionType.QUALIFYING, "Qualifying"),
    3: (SessionType.RACE, "Race"),
}


class NASCARCupConnector(Connector):
    """
    Connector for NASCAR Cup Series.
    Uses the public NASCAR CDN JSON feeds.
    """

    API_TEMPLATE = "https://cf.nascar.com/cacher/{year}/{series_id}/race_list_basic.json"
    NASCAR_SERIES_ID = 1  # Cup Series

    @property
    def id(self) -> str:
        return "nascar_cup_official"

    @property
    def name(self) -> str:
        return "NASCAR Cup Series (Official API)"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="nascar_cup",
                name="NASCAR Cup Series",
                category=SeriesCategory.STOCK,
                connector_id=self.id,
            )
        ]

    # ── fetch ────────────────────────────────────────────────────────

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "nascar_cup":
            raise ValueError(f"NASCAR Cup connector does not support: {series_id}")

        url = self.API_TEMPLATE.format(year=season, series_id=self.NASCAR_SERIES_ID)
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.nascar.com/",
        }

        try:
            resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            logger.error("Failed to fetch NASCAR Cup %d: %s", season, e)
            raise

        return RawSeriesPayload(
            content=resp.text,
            content_type="application/json",
            url=url,
            retrieved_at=datetime.utcnow(),
            metadata={"series_id": series_id, "season": season},
        )

    # ── extract ──────────────────────────────────────────────────────

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        try:
            races = json.loads(raw.content)
        except json.JSONDecodeError:
            logger.error("Failed to parse NASCAR API JSON")
            return []

        events: List[Event] = []
        for idx, race in enumerate(races, 1):
            # race_type_id: 1 = points race, 2 = exhibition, 3 = all-star
            evt = self._parse_race(race, idx, raw)
            if evt:
                events.append(evt)
        return events

    def _parse_race(self, race: Dict, idx: int, raw: RawSeriesPayload) -> Optional[Event]:
        name = race.get("race_name")
        if not name:
            return None

        race_date_str = race.get("race_date")
        if not race_date_str:
            return None

        race_dt = date_parser.parse(race_date_str)
        race_date = race_dt.date()

        # Track info
        track_name = race.get("track_name", "TBD")

        # Infer timezone from track name
        tz_name = self._track_timezone(track_name)

        # Parse sessions from the schedule sub-items
        sessions: List[Session] = []
        all_dates: set = set()
        schedule = race.get("schedule", [])

        for item in schedule:
            run_type = item.get("run_type", 0)
            if run_type not in _RUN_TYPE_MAP:
                continue  # skip logistics (run_type 0)

            stype, default_name = _RUN_TYPE_MAP[run_type]
            event_name = item.get("event_name", default_name).strip()

            start_utc = item.get("start_time_utc")
            if not start_utc:
                continue

            # Parse start time
            try:
                start_dt = date_parser.parse(start_utc)
                start_iso = start_dt.isoformat()
                all_dates.add(start_dt.date().isoformat())
            except Exception:
                start_iso = start_utc

            sessions.append(
                Session(
                    session_id=f"nascar_{race.get('race_id', idx)}_{run_type}",
                    type=stype,
                    name=event_name,
                    start=start_iso,
                    end="TBC",
                    status=SessionStatus.SCHEDULED,
                )
            )

        # Compute date range
        all_dates.add(race_date.isoformat())
        sorted_dates = sorted(all_dates)
        start_date = date_parser.parse(sorted_dates[0]).date()
        end_date = date_parser.parse(sorted_dates[-1]).date()

        season = raw.metadata.get("season", race_date.year)
        event_id = f"nascar_cup_{season}_r{idx}"

        return Event(
            event_id=event_id,
            series_id="nascar_cup",
            name=name,
            start_date=start_date,
            end_date=end_date,
            venue=Venue(
                circuit=track_name,
                city=None,
                country="US",
                timezone=tz_name,
            ),
            sessions=sessions,
            sources=[
                Source(
                    url=raw.url,
                    provider_name=self.name,
                    retrieved_at=raw.retrieved_at,
                    extraction_method="api",
                )
            ],
        )

    @staticmethod
    def _track_timezone(track_name: str) -> str:
        """Map NASCAR track to timezone."""
        t = track_name.lower()
        if any(k in t for k in ["daytona", "homestead", "miami"]):
            return "America/New_York"
        if any(k in t for k in ["talladega", "atlanta", "darlington", "martinsville",
                                 "bristol", "charlotte", "richmond", "north wilkesboro",
                                 "bowman gray"]):
            return "America/New_York"
        if any(k in t for k in ["chicago", "nashville", "michigan", "indianapolis",
                                 "iowa", "kansas", "gateway"]):
            return "America/Chicago"
        if any(k in t for k in ["texas", "cota", "circuit of the americas"]):
            return "America/Chicago"
        if any(k in t for k in ["phoenix", "las vegas"]):
            return "America/Los_Angeles"
        if any(k in t for k in ["sonoma", "portland"]):
            return "America/Los_Angeles"
        if any(k in t for k in ["watkins glen", "new hampshire", "pocono", "dover"]):
            return "America/New_York"
        return "America/New_York"  # default to Eastern
