"""
Formula E Connector using the official PulseLive API.
API Base: https://api.formula-e.pulselive.com/formula-e/v1
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

# Maps user-facing season year → FE championship name
# FE seasons span two calendar years (e.g. 2025-2026 season)
_SEASON_NAME_MAP = {
    2026: "2025-2026",
    2025: "2024-2025",
    2024: "2023-2024",
    2023: "2022-2023",
    2022: "2021-2022",
}

# Session types we want to keep
_KEEP_TYPES = {"PRACTICE", "QUALIFYING", "RACE"}


class FormulaEConnector(Connector):
    """
    Connector for ABB FIA Formula E World Championship.
    Uses the PulseLive REST API (same infra as MotoGP).
    """

    API_BASE = "https://api.formula-e.pulselive.com/formula-e/v1"

    @property
    def id(self) -> str:
        return "formula_e_official"

    @property
    def name(self) -> str:
        return "Formula E Official API"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="formula_e",
                name="ABB FIA Formula E World Championship",
                category=SeriesCategory.OPENWHEEL,
                connector_id=self.id,
            )
        ]

    # ── helpers ──────────────────────────────────────────────────────

    def _api_get(self, path: str, **params) -> Any:
        """GET from FE API and return parsed JSON."""
        url = f"{self.API_BASE}/{path}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        }
        resp = httpx.get(url, params=params, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()

    def _get_championship_id(self, season: int) -> Optional[str]:
        """Look up the championship UUID for a season year."""
        try:
            data = self._api_get("championships")
            championships = data.get("championships", [])

            # Try exact match on name  e.g. "SEASON 2025-2026"
            target_name = _SEASON_NAME_MAP.get(season, f"{season - 1}-{season}")
            for c in championships:
                if target_name in c.get("name", ""):
                    return c["id"]

            # Fallback: latest championship
            if championships:
                return championships[-1]["id"]

        except Exception as e:
            logger.error("Failed to fetch FE championships: %s", e)
        return None

    # ── fetch ────────────────────────────────────────────────────────

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "formula_e":
            raise ValueError(f"FormulaE connector does not support: {series_id}")

        champ_id = self._get_championship_id(season)
        if not champ_id:
            raise ValueError(f"Could not find FE championship for season {season}")

        data = self._api_get("races", championshipId=champ_id)
        races = data.get("races", [])
        logger.info("FE API returned %d races for season %s", len(races), season)

        # Enrich each race with session details (needs individual requests)
        for i, race in enumerate(races):
            try:
                detail = self._api_get(f"races/{race['id']}")
                race["sessions"] = detail.get("sessions", [])
            except Exception:
                race["sessions"] = []

        return RawSeriesPayload(
            content=json.dumps(races),
            content_type="application/json",
            url=f"{self.API_BASE}/races?championshipId={champ_id}",
            retrieved_at=datetime.utcnow(),
            metadata={"series_id": series_id, "season": season, "championship_id": champ_id},
        )

    # ── extract ──────────────────────────────────────────────────────

    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        try:
            races = json.loads(raw.content)
        except json.JSONDecodeError:
            logger.error("Failed to parse FE API JSON")
            return []

        events: List[Event] = []
        for race in races:
            evt = self._parse_race(race, raw)
            if evt:
                events.append(evt)
        return events

    def _parse_race(self, race: Dict, raw: RawSeriesPayload) -> Optional[Event]:
        name = race.get("name")
        if not name:
            return None

        race_date_str = race.get("date")
        if not race_date_str:
            return None

        start_date = date_parser.parse(race_date_str).date()
        end_date = start_date

        # Venue
        circuit_obj = race.get("circuit", {}) or {}
        circuit_name = circuit_obj.get("circuitFullName") or circuit_obj.get("circuitName") or ""
        city = race.get("city", "")
        country_code = race.get("country", "")

        tz_name = "UTC"
        try:
            tz_name, _ = infer_timezone_from_location(city=city, country=country_code)
            if not tz_name:
                tz_name = "UTC"
        except Exception:
            pass

        # Sessions
        sessions: List[Session] = []
        all_session_dates: set = set()

        for sess_data in race.get("sessions", []):
            session = self._parse_session(sess_data)
            if session:
                sessions.append(session)
                if session.start and len(str(session.start)) >= 10:
                    all_session_dates.add(str(session.start)[:10])

        # Fix date range from sessions
        if all_session_dates:
            sorted_dates = sorted(all_session_dates)
            start_date = date_parser.parse(sorted_dates[0]).date()
            end_date = date_parser.parse(sorted_dates[-1]).date()

        round_num = race.get("sequence", 0)
        season = raw.metadata.get("season", start_date.year)
        event_id = f"fe_{season}_r{round_num}"

        return Event(
            event_id=event_id,
            series_id="formula_e",
            name=name,
            start_date=start_date,
            end_date=end_date,
            venue=Venue(
                circuit=circuit_name or city or name,
                city=city or None,
                country=country_code or "Unknown",
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

    def _parse_session(self, s: Dict) -> Optional[Session]:
        """Parse a FE API session dict.
        
        FE API times:
        - startTime / finishTime / contingencyFinishTime are UTC
        - offsetGMT is the local track offset
        Website shows: startTime + offset (start), contingencyFinishTime + offset (end)
        """
        name = s.get("sessionName", "")
        if not name:
            return None

        # Determine type
        name_upper = name.upper()
        if "FREE PRACTICE" in name_upper or "PRACTICE" in name_upper:
            stype = SessionType.PRACTICE
        elif "QUALIFYING" in name_upper:
            stype = SessionType.QUALIFYING
        elif "RACE" in name_upper or "E-PRIX" in name_upper:
            stype = SessionType.RACE
        else:
            return None  # skip shakedown, group quali sub-sessions, etc.

        # Build local timestamps
        sess_date = s.get("sessionDate")
        start_time = s.get("startTime")
        offset = s.get("offsetGMT", "00:00")

        if not sess_date or not start_time:
            return None

        start_iso = self._utc_to_local_iso(sess_date, start_time, offset)
        end_iso = None
        finish = s.get("contingencyFinishTime") or s.get("finishTime")
        if finish:
            end_iso = self._utc_to_local_iso(sess_date, finish, offset)

        return Session(
            session_id=s.get("id", ""),
            type=stype,
            name=name,
            start=start_iso,
            end=end_iso or "TBC",
            status=SessionStatus.SCHEDULED,
        )

    @staticmethod
    def _utc_to_local_iso(sess_date: str, utc_time: str, offset_str: str) -> str:
        """Convert UTC HH:MM + offset → local ISO string."""
        try:
            parts = offset_str.split(":")
            off_h, off_m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            offset_td = timedelta(hours=off_h, minutes=off_m)

            tp = utc_time.split(":")
            utc_h, utc_m = int(tp[0]), int(tp[1]) if len(tp) > 1 else 0

            utc_dt = datetime.strptime(f"{sess_date} {utc_h:02d}:{utc_m:02d}", "%Y-%m-%d %H:%M")
            local_dt = utc_dt + offset_td

            return f"{local_dt.strftime('%Y-%m-%dT%H:%M:%S')}+{off_h:02d}:{off_m:02d}"
        except Exception:
            return f"{sess_date}T{utc_time}:00+{offset_str}"
