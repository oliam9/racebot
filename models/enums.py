"""
Enumerations for motorsport data models.
"""

from enum import Enum


class SessionType(str, Enum):
    """Type of motorsport session."""
    PRACTICE = "PRACTICE"
    QUALIFYING = "QUALIFYING"
    RACE = "RACE"
    SPRINT = "SPRINT"
    WARMUP = "WARMUP"
    TEST = "TEST"
    STAGE = "STAGE"
    RALLY_STAGE = "RALLY_STAGE"
    RACE_1 = "RACE_1"
    RACE_2 = "RACE_2"
    FEATURE = "FEATURE"
    HEAT = "HEAT"
    OTHER = "OTHER"


class SessionStatus(str, Enum):
    """Status of a session."""
    SCHEDULED = "SCHEDULED"
    UPDATED = "UPDATED"
    CANCELLED = "CANCELLED"
    TBD = "TBD"


class SeriesCategory(str, Enum):
    """Category of motorsport series."""
    OPENWHEEL = "OPENWHEEL"
    ENDURANCE = "ENDURANCE"
    RALLY = "RALLY"
    MOTORCYCLE = "MOTORCYCLE"
    GT = "GT"
    TOURING = "TOURING"
    FORMULA = "FORMULA"
    SPORTCAR = "SPORTCAR"
    STOCK = "STOCK"
    OTHER = "OTHER"
