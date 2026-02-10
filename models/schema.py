"""
Pydantic data models for motorsport data canonical schema.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator
import pytz
from .enums import SessionType, SessionStatus, SeriesCategory


class Source(BaseModel):
    """Data provenance information."""
    url: str = Field(..., description="Source URL")
    provider_name: str = Field(..., description="Provider/connector name")
    retrieved_at: datetime = Field(..., description="Timestamp when data was retrieved")
    raw_ref: Optional[str] = Field(None, description="Reference to raw data (optional)")
    extraction_method: Optional[str] = Field(
        None, 
        description="Extraction method: 'http', 'playwright_network', 'playwright_dom'"
    )
    discovered_endpoints: List[str] = Field(
        default_factory=list,
        description="API endpoints discovered during extraction"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.indycar.com/schedule",
                "provider_name": "IndyCar Official",
                "retrieved_at": "2024-03-15T10:30:00Z",
                "raw_ref": "indycar_2024_schedule.ics",
                "extraction_method": "http",
                "discovered_endpoints": []
            }
        }


class Venue(BaseModel):
    """Event venue information."""
    circuit: Optional[str] = Field(None, description="Circuit/track name")
    city: Optional[str] = Field(None, description="City")
    region: Optional[str] = Field(None, description="State/province/region")
    country: str = Field(..., description="Country")
    timezone: str = Field(..., description="IANA timezone identifier")
    lat: Optional[float] = Field(None, ge=-90, le=90, description="Latitude")
    lon: Optional[float] = Field(None, ge=-180, le=180, description="Longitude")
    inferred_timezone: bool = Field(False, description="Whether timezone was inferred")
    
    @field_validator('timezone')
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate IANA timezone."""
        if v not in pytz.all_timezones:
            raise ValueError(f"Invalid IANA timezone: {v}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "circuit": "Indianapolis Motor Speedway",
                "city": "Indianapolis",
                "region": "Indiana",
                "country": "United States",
                "timezone": "America/Indiana/Indianapolis",
                "lat": 39.795,
                "lon": -86.235,
                "inferred_timezone": False
            }
        }


class Session(BaseModel):
    """Motorsport session."""
    session_id: str = Field(..., description="Unique session ID within event")
    type: SessionType = Field(..., description="Session type")
    name: str = Field(..., description="Session name")
    start: Optional[str] = Field(None, description="Start time (ISO-8601 with offset)")
    end: Optional[str] = Field(None, description="End time (ISO-8601 with offset)")
    status: SessionStatus = Field(SessionStatus.SCHEDULED, description="Session status")
    notes: Optional[str] = Field(None, description="Additional notes")
    
    # Optional fields for specialized session types
    laps_planned: Optional[int] = Field(None, ge=0, description="Planned number of laps")
    distance_km: Optional[float] = Field(None, ge=0, description="Distance in kilometers")
    stage_number: Optional[int] = Field(None, ge=1, description="Stage number (rally/NASCAR)")
    
    @field_validator('start', 'end')
    @classmethod
    def validate_iso_datetime(cls, v: Optional[str]) -> Optional[str]:
        """Validate ISO-8601 datetime with offset."""
        if v is None:
            return v
        try:
            # Try parsing to ensure it's valid ISO-8601
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid ISO-8601 datetime: {v}")
    
    @model_validator(mode='after')
    def validate_times(self) -> 'Session':
        """Validate end is after start."""
        if self.start and self.end:
            try:
                start_dt = datetime.fromisoformat(self.start.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(self.end.replace('Z', '+00:00'))
                if end_dt <= start_dt:
                    raise ValueError(f"End time must be after start time")
            except ValueError:
                pass  # Let individual validators handle format errors
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "indy500_2024_race",
                "type": "RACE",
                "name": "Indianapolis 500",
                "start": "2024-05-26T12:45:00-04:00",
                "end": "2024-05-26T16:30:00-04:00",
                "status": "SCHEDULED",
                "laps_planned": 200,
                "distance_km": 804.672
            }
        }


class Event(BaseModel):
    """Motorsport event."""
    event_id: str = Field(..., description="Unique stable event ID")
    series_id: str = Field(..., description="Parent series ID")
    name: str = Field(..., description="Event name")
    start_date: date = Field(..., description="Event start date (local)")
    end_date: date = Field(..., description="Event end date (local)")
    venue: Venue = Field(..., description="Venue information")
    sessions: List[Session] = Field(default_factory=list, description="Event sessions")
    sources: List[Source] = Field(default_factory=list, description="Data sources")
    last_verified_at: Optional[datetime] = Field(None, description="Last verification timestamp")
    
    @model_validator(mode='after')
    def validate_dates(self) -> 'Event':
        """Validate end_date is not before start_date."""
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return self.model_dump(mode='json')
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """Create from dictionary (JSON import)."""
        return cls.model_validate(data)
    
    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "indycar_2024_indy500",
                "series_id": "indycar",
                "name": "Indianapolis 500",
                "start_date": "2024-05-25",
                "end_date": "2024-05-26",
                "venue": {
                    "circuit": "Indianapolis Motor Speedway",
                    "city": "Indianapolis",
                    "region": "Indiana",
                    "country": "United States",
                    "timezone": "America/Indiana/Indianapolis"
                },
                "sessions": []
            }
        }


class Series(BaseModel):
    """Motorsport series."""
    series_id: str = Field(..., description="Unique stable series ID (slug)")
    name: str = Field(..., description="Series name")
    season: int = Field(..., ge=1900, le=2100, description="Season year")
    category: SeriesCategory = Field(..., description="Series category")
    events: List[Event] = Field(default_factory=list, description="Series events")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON export."""
        return self.model_dump(mode='json')
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Series':
        """Create from dictionary (JSON import)."""
        return cls.model_validate(data)
    
    class Config:
        json_schema_extra = {
            "example": {
                "series_id": "indycar",
                "name": "NTT IndyCar Series",
                "season": 2024,
                "category": "OPENWHEEL",
                "events": []
            }
        }


class ExportManifest(BaseModel):
    """Export metadata."""
    exported_at: datetime = Field(..., description="Export timestamp")
    series_id: str = Field(..., description="Series ID")
    season: int = Field(..., description="Season year")
    sha256: str = Field(..., description="SHA-256 hash of exported data")
    provenance_summary: Dict[str, int] = Field(
        default_factory=dict,
        description="Summary of data sources (provider -> event count)"
    )
    validation_warnings: int = Field(0, ge=0, description="Number of validation warnings")
    validation_errors: int = Field(0, ge=0, description="Number of validation errors")
    
    class Config:
        json_schema_extra = {
            "example": {
                "exported_at": "2024-03-15T14:30:00Z",
                "series_id": "indycar",
                "season": 2024,
                "sha256": "abc123...",
                "provenance_summary": {"IndyCar Official": 17},
                "validation_warnings": 2,
                "validation_errors": 0
            }
        }


class SeriesDescriptor(BaseModel):
    """Descriptor for available series from a connector."""
    series_id: str = Field(..., description="Series ID")
    name: str = Field(..., description="Display name")
    category: SeriesCategory = Field(..., description="Series category")
    connector_id: str = Field(..., description="Connector that provides this series")
    
    class Config:
        json_schema_extra = {
            "example": {
                "series_id": "indycar",
                "name": "NTT IndyCar Series",
                "category": "OPENWHEEL",
                "connector_id": "indycar_official"
            }
        }
