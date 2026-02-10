"""
Tests for DB-compatible JSON export.
"""

import pytest
from datetime import date, datetime
from ui.db_export import (
    generate_db_export,
    _map_category,
    _map_session_type,
    _country_to_code,
    _deterministic_uuid,
    build_circuit_row,
    build_event_row,
    build_session_row,
)
from models.schema import Series, Event, Session, Venue, Source
from models.enums import SessionType, SessionStatus, SeriesCategory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_venue(**overrides):
    defaults = {
        "circuit": "Indianapolis Motor Speedway",
        "city": "Indianapolis",
        "region": "Indiana",
        "country": "United States",
        "timezone": "America/Indiana/Indianapolis",
        "lat": 39.795,
        "lon": -86.235,
    }
    defaults.update(overrides)
    return Venue(**defaults)


def _make_session(idx=1, **overrides):
    defaults = {
        "session_id": f"sess_{idx}",
        "type": SessionType.RACE,
        "name": f"Race {idx}",
        "start": "2026-05-25T12:00:00-04:00",
        "end": "2026-05-25T15:00:00-04:00",
        "status": SessionStatus.SCHEDULED,
    }
    defaults.update(overrides)
    return Session(**defaults)


def _make_event(idx=1, sessions=None, **overrides):
    defaults = {
        "event_id": f"indycar_2026_event{idx}",
        "series_id": "indycar",
        "name": f"Event {idx}",
        "start_date": date(2026, 5, 25),
        "end_date": date(2026, 5, 26),
        "venue": _make_venue(),
        "sessions": sessions or [_make_session()],
        "sources": [],
    }
    defaults.update(overrides)
    return Event(**defaults)


def _make_series(events=None, **overrides):
    defaults = {
        "series_id": "indycar",
        "name": "NTT IndyCar Series",
        "season": 2026,
        "category": SeriesCategory.OPENWHEEL,
        "events": events or [_make_event()],
    }
    defaults.update(overrides)
    return Series(**defaults)


# ---------------------------------------------------------------------------
# Enum mapping tests
# ---------------------------------------------------------------------------

class TestEnumMapping:
    def test_category_openwheel(self):
        assert _map_category(SeriesCategory.OPENWHEEL) == "open_wheel"

    def test_category_formula(self):
        assert _map_category(SeriesCategory.FORMULA) == "open_wheel"

    def test_category_gt(self):
        assert _map_category(SeriesCategory.GT) == "gt"

    def test_category_other(self):
        assert _map_category(SeriesCategory.OTHER) == "other"

    def test_session_practice(self):
        assert _map_session_type(SessionType.PRACTICE) == "practice"

    def test_session_race(self):
        assert _map_session_type(SessionType.RACE) == "race"

    def test_session_qualifying(self):
        assert _map_session_type(SessionType.QUALIFYING) == "qualifying"

    def test_session_sprint(self):
        assert _map_session_type(SessionType.SPRINT) == "sprint_race"

    def test_session_warmup(self):
        assert _map_session_type(SessionType.WARMUP) == "warmup"


# ---------------------------------------------------------------------------
# Country code tests
# ---------------------------------------------------------------------------

class TestCountryCode:
    def test_full_name(self):
        assert _country_to_code("United States") == "US"

    def test_already_code(self):
        assert _country_to_code("US") == "US"

    def test_case_insensitive(self):
        assert _country_to_code("united kingdom") == "GB"

    def test_unknown_fallback(self):
        code = _country_to_code("Narnia")
        assert len(code) == 2  # falls back to first 2 chars


# ---------------------------------------------------------------------------
# Deterministic UUID tests
# ---------------------------------------------------------------------------

class TestDeterministicUUID:
    def test_same_input_same_output(self):
        a = _deterministic_uuid("circuit", "Indianapolis Motor Speedway")
        b = _deterministic_uuid("circuit", "Indianapolis Motor Speedway")
        assert a == b

    def test_different_input_different_output(self):
        a = _deterministic_uuid("circuit", "Indianapolis Motor Speedway")
        b = _deterministic_uuid("circuit", "Barber Motorsports Park")
        assert a != b


# ---------------------------------------------------------------------------
# Full export test
# ---------------------------------------------------------------------------

class TestFullExport:
    def test_export_structure(self):
        series = _make_series()
        champ_id = "550e8400-e29b-41d4-a716-446655440000"
        result = generate_db_export(series, champ_id)

        assert "championships" in result
        assert "circuits" in result
        assert "championship_events" in result
        assert "championship_event_sessions" in result

    def test_championship_uses_provided_id(self):
        series = _make_series()
        champ_id = "550e8400-e29b-41d4-a716-446655440000"
        result = generate_db_export(series, champ_id)

        assert result["championships"][0]["id"] == champ_id

    def test_events_linked_to_championship(self):
        series = _make_series()
        champ_id = "550e8400-e29b-41d4-a716-446655440000"
        result = generate_db_export(series, champ_id)

        for ev in result["championship_events"]:
            assert ev["championship_id"] == champ_id

    def test_sessions_linked_to_events(self):
        series = _make_series()
        champ_id = "550e8400-e29b-41d4-a716-446655440000"
        result = generate_db_export(series, champ_id)

        event_ids = {ev["id"] for ev in result["championship_events"]}
        for sess in result["championship_event_sessions"]:
            assert sess["championship_event_id"] in event_ids

    def test_circuit_deduplication(self):
        """Two events at the same circuit should produce one circuit row."""
        e1 = _make_event(idx=1)
        e2 = _make_event(idx=2)  # same venue
        series = _make_series(events=[e1, e2])
        champ_id = "550e8400-e29b-41d4-a716-446655440000"
        result = generate_db_export(series, champ_id)

        assert len(result["circuits"]) == 1

    def test_circuit_country_code(self):
        series = _make_series()
        champ_id = "550e8400-e29b-41d4-a716-446655440000"
        result = generate_db_export(series, champ_id)

        circuit = result["circuits"][0]
        assert circuit["country_code"] == "US"

    def test_event_round_numbers(self):
        e1 = _make_event(idx=1, venue=_make_venue(circuit="Track A"))
        e2 = _make_event(idx=2, venue=_make_venue(circuit="Track B"))
        series = _make_series(events=[e1, e2])
        champ_id = "550e8400-e29b-41d4-a716-446655440000"
        result = generate_db_export(series, champ_id)

        rounds = [ev["round_number"] for ev in result["championship_events"]]
        assert rounds == [1, 2]

    def test_session_type_mapped(self):
        series = _make_series()
        champ_id = "550e8400-e29b-41d4-a716-446655440000"
        result = generate_db_export(series, champ_id)

        sess = result["championship_event_sessions"][0]
        assert sess["session_type"] == "race"

    def test_cancelled_session(self):
        session = _make_session(status=SessionStatus.CANCELLED)
        event = _make_event(sessions=[session])
        series = _make_series(events=[event])
        champ_id = "550e8400-e29b-41d4-a716-446655440000"
        result = generate_db_export(series, champ_id)

        sess = result["championship_event_sessions"][0]
        assert sess["is_cancelled"] is True
