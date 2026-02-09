"""
Timezone utilities for validation and inference.
"""

from datetime import datetime
from typing import Optional, Tuple
import pytz
from timezonefinder import TimezoneFinder


# Initialize timezone finder (singleton)
_tf = TimezoneFinder()


def validate_iana_timezone(tz_str: str) -> bool:
    """
    Validate if string is a valid IANA timezone identifier.
    
    Args:
        tz_str: Timezone string to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Use common_timezones to exclude deprecated abbreviations like EST, PST
    return tz_str in pytz.common_timezones or tz_str == "UTC"


def infer_timezone_from_location(
    country: Optional[str] = None,
    city: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None
) -> Tuple[Optional[str], bool]:
    """
    Infer IANA timezone from location data.
    
    Priority:
    1. If lat/lon provided, use TimezoneFinder
    2. If country/city provided, attempt lookup in common timezones
    
    Args:
        country: Country name
        city: City name
        lat: Latitude
        lon: Longitude
        
    Returns:
        Tuple of (timezone_str, is_inferred)
        Returns (None, False) if unable to infer
    """
    # Try lat/lon first (most accurate)
    if lat is not None and lon is not None:
        tz_str = _tf.timezone_at(lat=lat, lng=lon)
        if tz_str:
            return (tz_str, True)
    
    # Fallback: Common country/city mappings
    # This is a simplified version - in production, use a comprehensive database
    common_mappings = {
        ("United States", "Indianapolis"): "America/Indiana/Indianapolis",
        ("United States", "Detroit"): "America/Detroit",
        ("United States", "Long Beach"): "America/Los_Angeles",
        ("United States", "St. Petersburg"): "America/New_York",
        ("United States", "Phoenix"): "America/Phoenix",
        ("United States", "Nashville"): "America/Chicago",
        ("United States", "Miami"): "America/New_York",
        ("United States", "Austin"): "America/Chicago",
        ("United States", "Portland"): "America/Los_Angeles",
        ("United States", "Milwaukee"): "America/Chicago",
        ("United States", "Monterey"): "America/Los_Angeles",
        ("Canada", "Toronto"): "America/Toronto",
        ("Canada", "Montreal"): "America/Montreal",
        ("Canada", "Edmonton"): "America/Edmonton",
        ("Japan", "Tokyo"): "Asia/Tokyo",
        ("United Kingdom", "Silverstone"): "Europe/London",
        ("Italy", "Monza"): "Europe/Rome",
        ("Monaco", "Monte Carlo"): "Europe/Monaco",
        ("Belgium", "Spa"): "Europe/Brussels",
        ("Austria", "Spielberg"): "Europe/Vienna",
        ("Hungary", "Budapest"): "Europe/Budapest",
        ("Netherlands", "Zandvoort"): "Europe/Amsterdam",
        ("Mexico", "Mexico City"): "America/Mexico_City",
        ("Brazil", "São Paulo"): "America/Sao_Paulo",
        ("Singapore", "Singapore"): "Asia/Singapore",
        ("Australia", "Melbourne"): "Australia/Melbourne",
        ("Australia", "Adelaide"): "Australia/Adelaide",
        ("UAE", "Abu Dhabi"): "Asia/Dubai",
        ("Bahrain", "Sakhir"): "Asia/Bahrain",
        ("Saudi Arabia", "Jeddah"): "Asia/Riyadh",
    }
    
    if country and city:
        key = (country, city)
        if key in common_mappings:
            return (common_mappings[key], True)
    
    # Unable to infer
    return (None, False)


def parse_iso_datetime(iso_str: str) -> Optional[datetime]:
    """
    Parse ISO-8601 datetime string with timezone.
    
    Args:
        iso_str: ISO-8601 formatted datetime string
        
    Returns:
        Parsed datetime object or None if invalid
    """
    try:
        # Handle 'Z' suffix (UTC)
        normalized = iso_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(normalized)
        
        # For our purposes, we require timezone information
        # Reject date-only strings (they parse but aren't what we want)
        if 'T' not in iso_str and ':' not in iso_str:
            return None
        
        return dt
    except (ValueError, AttributeError):
        return None


def check_dst_transition(dt: datetime, tz_str: str) -> bool:
    """
    Check if datetime falls on a DST transition boundary.
    
    Args:
        dt: Datetime to check
        tz_str: IANA timezone identifier
        
    Returns:
        True if on DST transition, False otherwise
    """
    try:
        tz = pytz.timezone(tz_str)
        # Check if datetime is ambiguous or doesn't exist due to DST
        try:
            tz.localize(dt.replace(tzinfo=None), is_dst=None)
            return False
        except pytz.exceptions.AmbiguousTimeError:
            return True
        except pytz.exceptions.NonExistentTimeError:
            return True
    except Exception:
        return False


def sessions_overlap(
    start1: str,
    end1: Optional[str],
    start2: str,
    end2: Optional[str]
) -> bool:
    """
    Check if two sessions overlap in time.
    
    Args:
        start1: Start time of session 1 (ISO-8601)
        end1: End time of session 1 (ISO-8601, optional)
        start2: Start time of session 2 (ISO-8601)
        end2: End time of session 2 (ISO-8601, optional)
        
    Returns:
        True if sessions overlap, False otherwise
    """
    # Parse datetimes
    dt_start1 = parse_iso_datetime(start1)
    dt_start2 = parse_iso_datetime(start2)
    
    if not dt_start1 or not dt_start2:
        return False  # Can't determine without valid times
    
    # If either session doesn't have an end time, we can't definitively say they overlap
    if not end1 or not end2:
        return False
    
    dt_end1 = parse_iso_datetime(end1)
    dt_end2 = parse_iso_datetime(end2)
    
    if not dt_end1 or not dt_end2:
        return False
    
    # Check for overlap: session1.start < session2.end AND session2.start < session1.end
    return dt_start1 < dt_end2 and dt_start2 < dt_end1
