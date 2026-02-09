"""
Tests for validation rules.
"""

import pytest
from datetime import date, datetime
from models.schema import Series, Event, Session, Venue, Source
from models.enums import SessionType, SessionStatus, SeriesCategory
from validators.rules import DataValidator, ValidationResult


@pytest.fixture
def sample_venue():
    """Create a sample venue."""
    return Venue(
        circuit="Test Circuit",
        city="Test City",
        country="United States",
        timezone="America/New_York",
        inferred_timezone=False
    )


@pytest.fixture
def sample_session():
    """Create a sample valid session."""
    return Session(
        session_id="test_session_1",
        type=SessionType.RACE,
        name="Test Race",
        start="2024-05-26T12:00:00-04:00",
        end="2024-05-26T14:00:00-04:00",
        status=SessionStatus.SCHEDULED
    )


@pytest.fixture
def sample_event(sample_venue, sample_session):
    """Create a sample event."""
    return Event(
        event_id="test_event_1",
        series_id="test_series",
        name="Test Event",
        start_date=date(2024, 5, 26),
        end_date=date(2024, 5, 26),
        venue=sample_venue,
        sessions=[sample_session],
        sources=[
            Source(
                url="https://example.com/calendar",
                provider_name="Test Provider",
                retrieved_at=datetime.utcnow()
            )
        ]
    )


@pytest.fixture
def sample_series(sample_event):
    """Create a sample series."""
    return Series(
        series_id="test_series",
        name="Test Series",
        season=2024,
        category=SeriesCategory.OPENWHEEL,
        events=[sample_event]
    )


def test_validate_valid_series(sample_series):
    """Test validation of a valid series."""
    validator = DataValidator()
    result = validator.validate_series(sample_series)
    
    assert result.is_valid
    assert len(result.errors) == 0


def test_validate_invalid_timezone():
    """Test validation catches invalid timezone."""
    # Pydantic will reject invalid timezone at model creation time
    with pytest.raises(Exception):  # ValidationError from Pydantic
        venue = Venue(
            circuit="Test",
            city="Test",
            country="Test",
            timezone="INVALID/TIMEZONE",
            inferred_timezone=False
        )


def test_validate_missing_session_name():
    """Test validation catches missing session name."""
    session = Session(
        session_id="test",
        type=SessionType.RACE,
        name="",  # Empty name
        start="2024-05-26T12:00:00-04:00",
        end="2024-05-26T14:00:00-04:00",
        status=SessionStatus.SCHEDULED
    )
    
    validator = DataValidator()
    result = validator.validate_session(session, "test_event")
    
    assert not result.is_valid
    assert any("name" in e.message.lower() for e in result.errors)


def test_validate_invalid_time_format():
    """Test validation catches invalid time format."""
    # Pydantic validator will catch this at model creation
    with pytest.raises(Exception):  # ValidationError from Pydantic
        session = Session(
            session_id="test",
            type=SessionType.RACE,
            name="Test",
            start="2024-05-26 12:00:00",  # Invalid format (missing offset)
            end="2024-05-26T14:00:00-04:00",
            status=SessionStatus.SCHEDULED
        )


def test_validate_end_before_start():
    """Test validation catches end time before start time."""
    session = Session(
        session_id="test",
        type=SessionType.RACE,
        name="Test",
        start="2024-05-26T14:00:00-04:00",
        end="2024-05-26T12:00:00-04:00",  # Before start
        status=SessionStatus.SCHEDULED
    )
    
    validator = DataValidator()
    result = validator.validate_session(session, "test_event")
    
    assert not result.is_valid


def test_validate_tbd_session():
    """Test validation handles TBD sessions (warning, not error)."""
    session = Session(
        session_id="test",
        type=SessionType.RACE,
        name="Test",
        start=None,
        end=None,
        status=SessionStatus.TBD
    )
    
    validator = DataValidator()
    result = validator.validate_session(session, "test_event")
    
    # Should be valid (no errors), but may have warnings
    assert result.is_valid
    assert len(result.errors) == 0


def test_validate_overlapping_sessions(sample_venue):
    """Test detection of overlapping sessions."""
    session1 = Session(
        session_id="session1",
        type=SessionType.PRACTICE,
        name="Practice",
        start="2024-05-26T10:00:00-04:00",
        end="2024-05-26T12:00:00-04:00",
        status=SessionStatus.SCHEDULED
    )
    
    session2 = Session(
        session_id="session2",
        type=SessionType.QUALIFYING,
        name="Qualifying",
        start="2024-05-26T11:00:00-04:00",  # Overlaps with session1
        end="2024-05-26T13:00:00-04:00",
        status=SessionStatus.SCHEDULED
    )
    
    event = Event(
        event_id="test",
        series_id="test",
        name="Test",
        start_date=date(2024, 5, 26),
        end_date=date(2024, 5, 26),
        venue=sample_venue,
        sessions=[session1, session2],
        sources=[]
    )
    
    validator = DataValidator()
    result = validator.validate_event(event)
    
    # Should be valid (overlap is warning, not error)
    assert result.is_valid
    # But should have warning about overlap
    assert len(result.warnings) > 0
    assert any("overlap" in w.message.lower() for w in result.warnings)


def test_validate_duplicate_event_ids():
    """Test detection of duplicate event IDs."""
    event1 = Event(
        event_id="duplicate",
        series_id="test",
        name="Event 1",
        start_date=date(2024, 5, 26),
        end_date=date(2024, 5, 26),
        venue=Venue(
            circuit="Test",
            city="Test",
            country="US",
            timezone="America/New_York"
        ),
        sessions=[],
        sources=[]
    )
    
    event2 = Event(
        event_id="duplicate",  # Same ID
        series_id="test",
        name="Event 2",
        start_date=date(2024, 6, 15),
        end_date=date(2024, 6, 15),
        venue=Venue(
            circuit="Test 2",
            city="Test",
            country="US",
            timezone="America/New_York"
        ),
        sessions=[],
        sources=[]
    )
    
    series = Series(
        series_id="test",
        name="Test",
        season=2024,
        category=SeriesCategory.OPENWHEEL,
        events=[event1, event2]
    )
    
    validator = DataValidator()
    result = validator.validate_series(series)
    
    assert not result.is_valid
    assert any("duplicate" in e.message.lower() for e in result.errors)
