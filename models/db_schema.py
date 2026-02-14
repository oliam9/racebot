"""
Pydantic models matching the Supabase database schema exactly.
Used for validation, staging, and publishing.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, date
from uuid import UUID
from pydantic import BaseModel, Field, Json
from enum import Enum

class ChampionshipCategory(str, Enum):
    FORMULA = "formula"
    STOCK = "stock"
    ENDURANCE = "endurance"
    GT = "gt"
    RALLY = "rally"
    MOTORBIKE = "motorbike"
    TOURING = "touring"
    OTHER = "other"

class SessionType(str, Enum):
    PRACTICE = "practice"
    QUALIFYING = "qualifying"
    SPRINT = "sprint"
    RACE = "race"
    WARMUP = "warmup"
    OTHER = "other"
    SPRINT_QUALIFYING = "sprint_qualifying"

class Championship(BaseModel):
    id: UUID
    name: str
    short_name: str
    category: ChampionshipCategory
    logo_url: Optional[str] = None
    website_url: Optional[str] = None
    branding: Optional[Dict[str, Any]] = None  # JSONB
    is_active: bool = True
    display_order: int = 100
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class Circuit(BaseModel):
    id: UUID
    name: str
    full_name: Optional[str] = None
    short_name: Optional[str] = None
    country_code: Optional[str] = None
    city: Optional[str] = None
    timezone: Optional[str] = None
    location: Optional[Dict[str, Any]] = None  # JSONB (lat, lng)
    website_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ChampionshipEvent(BaseModel):
    id: Optional[UUID] = None  # Nullable for drafts/inserts
    championship_id: UUID
    circuit_id: Optional[UUID] = None
    name: str
    round_number: int
    season: int
    start_date: date
    end_date: date
    is_confirmed: bool = False
    is_cancelled: bool = False
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict) # JSONB
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ChampionshipEventSession(BaseModel):
    id: Optional[UUID] = None  # Nullable for drafts/inserts
    championship_event_id: Optional[UUID] = None # Nullable for drafts until parent created
    name: str
    session_type: SessionType
    start_time: Optional[datetime] = None # Timestamptz
    end_time: Optional[datetime] = None   # Timestamptz
    is_cancelled: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
