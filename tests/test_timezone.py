"""
Tests for timezone utilities.
"""

import pytest
from datetime import datetime
from validators.timezone_utils import (
    validate_iana_timezone,
    infer_timezone_from_location,
    parse_iso_datetime,
    sessions_overlap,
)


def test_validate_iana_timezone():
    """Test IANA timezone validation."""
    # Valid timezones
    assert validate_iana_timezone("America/New_York")
    assert validate_iana_timezone("Europe/London")
    assert validate_iana_timezone("Asia/Tokyo")
    assert validate_iana_timezone("UTC")
    
    # Invalid timezones
    assert not validate_iana_timezone("EST")
    assert not validate_iana_timezone("PST")
    assert not validate_iana_timezone("Invalid/Timezone")
    assert not validate_iana_timezone("")


def test_infer_timezone_from_location():
    """Test timezone inference from location data."""
    # Test with country and city
    tz, inferred = infer_timezone_from_location(
        country="United States",
        city="Indianapolis"
    )
    assert tz == "America/Indiana/Indianapolis"
    assert inferred is True
    
    # Test with unknown location
    tz, inferred = infer_timezone_from_location(
        country="Unknown",
        city="Unknown"
    )
    assert tz is None
    assert inferred is False
    
    # Test with lat/lon (if provided)
    tz, inferred = infer_timezone_from_location(
        lat=39.795,
        lon=-86.235
    )
    assert tz is not None
    assert inferred is True


def test_parse_iso_datetime():
    """Test ISO-8601 datetime parsing."""
    # Valid ISO strings
    dt = parse_iso_datetime("2024-05-26T12:45:00-04:00")
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 5
    assert dt.day == 26
    assert dt.hour == 12
    
    # With Z suffix (UTC)
    dt = parse_iso_datetime("2024-05-26T16:45:00Z")
    assert dt is not None
    
    # Invalid formats
    assert parse_iso_datetime("2024-05-26") is None  # Date only
    assert parse_iso_datetime("invalid") is None
    assert parse_iso_datetime("") is None


def test_sessions_overlap():
    """Test session overlap detection."""
    # Non-overlapping sessions
    assert not sessions_overlap(
        "2024-05-26T10:00:00-04:00",
        "2024-05-26T11:00:00-04:00",
        "2024-05-26T12:00:00-04:00",
        "2024-05-26T13:00:00-04:00"
    )
    
    # Overlapping sessions
    assert sessions_overlap(
        "2024-05-26T10:00:00-04:00",
        "2024-05-26T12:00:00-04:00",
        "2024-05-26T11:00:00-04:00",
        "2024-05-26T13:00:00-04:00"
    )
    
    # Fully contained
    assert sessions_overlap(
        "2024-05-26T10:00:00-04:00",
        "2024-05-26T14:00:00-04:00",
        "2024-05-26T11:00:00-04:00",
        "2024-05-26T12:00:00-04:00"
    )
    
    # Edge case: sessions with no end time
    assert not sessions_overlap(
        "2024-05-26T10:00:00-04:00",
        None,
        "2024-05-26T12:00:00-04:00",
        None
    )
