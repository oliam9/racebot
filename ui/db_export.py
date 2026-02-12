"""
DB-compatible JSON export — produces JSON matching the Supabase table schemas:
  - championships
  - circuits
  - championship_events
  - championship_event_sessions
"""

import json
import uuid
import hashlib
import streamlit as st
from datetime import datetime
from typing import Dict, List, Any, Optional

from models.schema import Series, Event, Session, Venue
from models.enums import SessionType, SeriesCategory
from database.supabase_client import get_supabase_client


# ---------------------------------------------------------------------------
# Namespace UUID for deterministic v5 generation
# ---------------------------------------------------------------------------
_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _deterministic_uuid(*parts: str) -> str:
    """Generate a deterministic UUID v5 from string parts."""
    combined = "|".join(str(p) for p in parts)
    return str(uuid.uuid5(_NAMESPACE, combined))


# ---------------------------------------------------------------------------
# Enum mappings  (app enum value → DB enum value)
# ---------------------------------------------------------------------------
CATEGORY_MAP: Dict[str, str] = {
    "OPENWHEEL": "open_wheel",
    "FORMULA": "open_wheel",
    "ENDURANCE": "endurance",
    "SPORTCAR": "endurance",
    "GT": "gt",
    "TOURING": "touring",
    "RALLY": "rally",
    "MOTORCYCLE": "motorcycle",
    "OTHER": "other",
}

SESSION_TYPE_MAP: Dict[str, str] = {
    "PRACTICE": "practice",
    "QUALIFYING": "qualifying",
    "RACE": "race",
    "RACE_1": "race",
    "RACE_2": "race",
    "FEATURE": "race",
    "SPRINT": "sprint_race",
    "HEAT": "sprint_race",
    "WARMUP": "warmup",
    "TEST": "testing",
    "STAGE": "other",
    "RALLY_STAGE": "other",
    "OTHER": "other",
}


def _map_category(cat: SeriesCategory) -> str:
    return CATEGORY_MAP.get(cat.value, "other")


def _map_session_type(st_enum: SessionType) -> str:
    return SESSION_TYPE_MAP.get(st_enum.value, "other")


# ---------------------------------------------------------------------------
# Country name → ISO-3166 alpha-2  (best-effort, no extra dependency)
# ---------------------------------------------------------------------------
_COUNTRY_CODES: Dict[str, str] = {
    "united states": "US", "usa": "US", "us": "US",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB", "england": "GB",
    "france": "FR", "germany": "DE", "italy": "IT", "spain": "ES",
    "australia": "AU", "canada": "CA", "japan": "JP", "brazil": "BR",
    "mexico": "MX", "china": "CN", "netherlands": "NL", "belgium": "BE",
    "austria": "AT", "switzerland": "CH", "portugal": "PT", "hungary": "HU",
    "monaco": "MC", "singapore": "SG", "bahrain": "BH", "saudi arabia": "SA",
    "qatar": "QA", "united arab emirates": "AE", "uae": "AE",
    "azerbaijan": "AZ", "turkey": "TR", "russia": "RU", "sweden": "SE",
    "finland": "FI", "norway": "NO", "denmark": "DK", "poland": "PL",
    "czech republic": "CZ", "czechia": "CZ", "south africa": "ZA",
    "new zealand": "NZ", "argentina": "AR", "chile": "CL", "colombia": "CO",
    "india": "IN", "malaysia": "MY", "thailand": "TH", "indonesia": "ID",
    "south korea": "KR", "korea": "KR", "vietnam": "VN", "ireland": "IE",
    "scotland": "GB", "wales": "GB",
}


def _country_to_code(country: str) -> str:
    """Convert country name to ISO-3166 alpha-2 code (best effort)."""
    if not country:
        return "XX"
    # Already a 2-letter code?
    if len(country) == 2 and country.isalpha():
        return country.upper()
    return _COUNTRY_CODES.get(country.strip().lower(), country[:2].upper())


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_circuit_row(venue: Venue, event_name: str) -> Dict[str, Any]:
    """Build a single circuits table row from a Venue."""
    circuit_name = venue.circuit or f"{venue.city or 'Unknown'} Circuit"
    circuit_id = _deterministic_uuid("circuit", circuit_name)

    location: Dict[str, Any] = {}
    if venue.lat is not None and venue.lon is not None:
        location = {"lat": venue.lat, "lng": venue.lon}

    return {
        "id": circuit_id,
        "name": circuit_name,
        "full_name": circuit_name,
        "short_name": (venue.circuit or venue.city or "")[:30] or None,
        "country_code": _country_to_code(venue.country),
        "city": venue.city,
        "timezone": venue.timezone,
        "location": location,
        "layout": None,
        "layout_svg": None,
        "google_share_url": None,
        "website_url": None,
        "phone": None,
        "layout_3d_url": None,
    }


def build_championship_row(series: Series) -> Dict[str, Any]:
    """Build a championships table row (user will override the id)."""
    return {
        "id": None,  # user must supply this
        "name": series.name,
        "short_name": series.series_id,
        "category": _map_category(series.category),
        "logo_url": None,
        "website_url": None,
        "branding": {},
        "is_active": True,
        "display_order": 100,
        "parent_championship_id": None,
    }


def build_event_row(
    event: Event,
    championship_id: str,
    circuit_id: Optional[str],
    round_number: int,
    season: int,
) -> Dict[str, Any]:
    """Build a championship_events table row."""
    event_uuid = _deterministic_uuid("event", championship_id, str(season), str(round_number))
    return {
        "id": event_uuid,
        "championship_id": championship_id,
        "circuit_id": circuit_id,
        "name": event.name,
        "round_number": round_number,
        "season": season,
        "start_date": event.start_date.isoformat(),
        "end_date": event.end_date.isoformat(),
        "is_confirmed": True,
        "is_cancelled": False,
        "metadata": {},
    }


def build_session_row(
    session: Session,
    event_uuid: str,
    session_index: int,
) -> Dict[str, Any]:
    """Build a championship_event_sessions table row."""
    session_uuid = _deterministic_uuid("session", event_uuid, str(session_index))
    return {
        "id": session_uuid,
        "championship_event_id": event_uuid,
        "name": session.name,
        "session_type": _map_session_type(session.type),
        "start_time": session.start,
        "end_time": session.end,
        "is_cancelled": session.status.value == "CANCELLED",
    }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def generate_db_export(series: Series, championship_id: str) -> Dict[str, Any]:
    """
    Transform a Series into DB-compatible JSON with four table arrays.

    Args:
        series: The racebot Series object.
        championship_id: The existing championship UUID from the DB.

    Returns:
        Dict with keys: championships, circuits, championship_events,
        championship_event_sessions.
    """
    # -- Championship row (for reference, user already has it in DB) --
    champ_row = build_championship_row(series)
    champ_row["id"] = championship_id

    # -- Circuits (deduplicated by name) --
    circuits_map: Dict[str, Dict[str, Any]] = {}  # circuit_name -> row
    for event in series.events:
        circuit_name = event.venue.circuit or f"{event.venue.city or 'Unknown'} Circuit"
        if circuit_name not in circuits_map:
            circuits_map[circuit_name] = build_circuit_row(event.venue, event.name)

    # -- Events + Sessions --
    event_rows: List[Dict[str, Any]] = []
    session_rows: List[Dict[str, Any]] = []

    for idx, event in enumerate(series.events, start=1):
        circuit_name = event.venue.circuit or f"{event.venue.city or 'Unknown'} Circuit"
        circuit_id = circuits_map[circuit_name]["id"]

        ev_row = build_event_row(event, championship_id, circuit_id, idx, series.season)
        event_rows.append(ev_row)

        for s_idx, session in enumerate(event.sessions, start=1):
            s_row = build_session_row(session, ev_row["id"], s_idx)
            session_rows.append(s_row)

    return {
        "championships": [champ_row],
        "circuits": list(circuits_map.values()),
        "championship_events": event_rows,
        "championship_event_sessions": session_rows,
    }


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def render_db_export_section(series: Series):
    """Render the DB export controls and download button."""
    with st.expander("🗄️ Export for Database", expanded=False):
        st.caption(
            "Push data directly to Supabase or generate JSON matching the table format. "
            "Paste the championship UUID from your database."
        )

        championship_id = st.text_input(
            "Championship UUID",
            placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000",
            key="db_export_champ_uuid",
            help="The UUID of the championship in your Supabase championships table.",
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("🚀 Push to Supabase", type="primary", key="db_push_btn", use_container_width=True):
                if not championship_id or not championship_id.strip():
                    st.error("Please paste a championship UUID first.")
                else:
                    push_to_supabase(series, championship_id.strip())

        with col2:
            if st.button("⬇️ Generate DB JSON", type="secondary", key="db_export_btn", use_container_width=True):
                if not championship_id or not championship_id.strip():
                    st.error("Please paste a championship UUID first.")
                else:
                    # Validate UUID format
                    try:
                        uuid.UUID(championship_id.strip())
                    except ValueError:
                        st.error("Invalid UUID format. Please paste a valid UUID.")
                        return

                    champ_id = championship_id.strip()
                    export_data = generate_db_export(series, champ_id)

                    json_str = json.dumps(export_data, indent=2, default=str)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"db_{series.series_id}_{series.season}_{timestamp}.json"

                    st.download_button(
                        label="📥 Download JSON",
                        data=json_str,
                        file_name=filename,
                        mime="application/json",
                        key="db_export_download",
                        use_container_width=True,
                    )

                    # Show summary
                    st.success(
                        f"**Ready!** "
                        f"{len(export_data['circuits'])} circuits · "
                        f"{len(export_data['championship_events'])} events · "
                        f"{len(export_data['championship_event_sessions'])} sessions"
                    )

                    # Preview
                    with st.expander("Preview JSON", expanded=False):
                        st.json(export_data)

def push_to_supabase(series: Series, championship_id: str):
    """Helper to push data to Supabase from the UI."""
    client = get_supabase_client()
    if not client:
        st.error("❌ Supabase client not initialized. Ensure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are in .env")
        return

    try:
        with st.spinner("Pushing to Supabase..."):
            export_data = generate_db_export(series, championship_id)

            # 1. Circuits
            for circuit in export_data['circuits']:
                client.table("circuits").upsert(circuit).execute()

            # 2. Championship
            for champ in export_data['championships']:
                client.table("championships").upsert(champ).execute()

            # 3. Events
            for event in export_data['championship_events']:
                client.table("championship_events").upsert(event).execute()

            # 4. Sessions
            if export_data['championship_event_sessions']:
                client.table("championship_event_sessions").upsert(export_data['championship_event_sessions']).execute()

        st.success(
            f"✅ **Success!** Pushed "
            f"{len(export_data['championship_events'])} events and "
            f"{len(export_data['championship_event_sessions'])} sessions."
        )
    except Exception as e:
        st.error(f"❌ Supabase Error: {str(e)}")
        with st.expander("Show full error"):
            st.code(str(e))
