"""
Home page — fetch data and display events with sessions inline.
"""

import streamlit as st
import json
from datetime import datetime
from connectors import list_available_series, get_connector
from models.schema import Series
from validators import DataValidator
from ui.export import render_download_button


def render():
    """Render the full page (with title) — used when app runs standalone."""
    st.title("🏁 MotorsportBot")
    render_content()


def render_content():
    """Render the connector content (without title) — used inside a tab."""
    # --- Compact fetch bar ---
    render_fetch_bar()

    # --- Show results directly ---
    if "series" in st.session_state and st.session_state.series:
        series = st.session_state.series
        st.markdown(
            f"**{series.name}** — {series.season} season · "
            f"{len(series.events)} events"
        )
        render_download_button(series)
        st.divider()
        render_events(series)
    else:
        st.info("Select a series and click **Fetch** to load the schedule.")


def render_fetch_bar():
    """Compact fetch controls in a single row."""
    available_series = list_available_series()
    if not available_series:
        st.error("No data connectors available")
        return

    series_options = {
        s.name: s.series_id for s in available_series
    }

    col1, col2, col3 = st.columns([3, 1.5, 1])
    with col1:
        selected_name = st.selectbox(
            "Series",
            options=list(series_options.keys()),
            key="series_selector",
            label_visibility="collapsed",
        )
    with col2:
        current_year = datetime.now().year
        season = st.number_input(
            "Season",
            min_value=2020,
            max_value=current_year + 1,
            value=current_year,
            key="season_input",
            label_visibility="collapsed",
        )
    with col3:
        if st.button("🚀 Fetch", type="primary", use_container_width=True):
            series_id = series_options[selected_name]
            fetch_data(series_id, season)


def render_events(series):
    """Display events as cards with sessions inside."""
    for idx, event in enumerate(series.events, start=1):
        with st.container(border=True):

            # Date range logic
            if event.start_date == event.end_date:
                date_str = event.start_date.strftime("%b %d, %Y").replace(" 0", " ")
            else:
                if event.start_date.month == event.end_date.month:
                    date_str = (
                        f"{event.start_date.strftime('%b %d').replace(' 0', ' ')}"
                        f" – {event.end_date.strftime('%d, %Y').lstrip('0')}"
                    )
                else:
                    date_str = (
                        f"{event.start_date.strftime('%b %d').replace(' 0', ' ')}"
                        f" – {event.end_date.strftime('%b %d, %Y').replace(' 0', ' ')}"
                    )

            # Venue logic
            venue_parts = []
            if event.venue.city:
                venue_parts.append(event.venue.city)
            if event.venue.region:
                venue_parts.append(event.venue.region)
            location_str = ", ".join(venue_parts) if venue_parts else "—"
            
            circuit_str = event.venue.circuit or "—"
            timezone_str = f"<code>{event.venue.timezone}</code>"

            # Custom HTML Layout
            html = f"""
            <div class="event-custom-header">
                <span class="event-badge">Race Week {idx}</span>
                <div class="event-name">{event.name}</div>
                <div class="event-meta-grid">
                    <div class="meta-item">
                        <span class="meta-label">Dates</span>
                        <span class="meta-value">📅 {date_str}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Circuit</span>
                        <span class="meta-value">🏁 {circuit_str}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Location</span>
                        <span class="meta-value">📍 {location_str}</span>
                    </div>
                    <div class="meta-item">
                        <span class="meta-label">Timezone</span>
                        <span class="meta-value">🕒 {timezone_str}</span>
                    </div>
                </div>
            </div>
            """
            
            st.markdown(html, unsafe_allow_html=True)

            # Sessions expander
            with st.expander("View Sessions", expanded=False):
                render_sessions(event)


def render_sessions(event):
    """Display sessions table for an event."""
    if not event.sessions:
        st.caption("No session details available — TBC")
        return

    # Group sessions by date
    from collections import OrderedDict

    sessions_by_date: OrderedDict = OrderedDict()
    for session in event.sessions:
        if session.start:
            try:
                dt = datetime.fromisoformat(session.start.replace("Z", "+00:00"))
                day_key = dt.strftime("%A, %b %d")
            except ValueError:
                day_key = "TBC"
        else:
            day_key = "TBC"
        sessions_by_date.setdefault(day_key, []).append(session)

    for day, day_sessions in sessions_by_date.items():
        st.markdown(f"**{day}**")

        rows = []
        for s in day_sessions:
            # Format time
            if s.start:
                try:
                    dt = datetime.fromisoformat(s.start.replace("Z", "+00:00"))
                    time_str = dt.strftime("%I:%M %p").lstrip('0')
                except ValueError:
                    time_str = "TBC"
            else:
                time_str = "TBC"

            rows.append(
                {
                    "Session": s.name,
                    "Time": time_str,
                    "Type": s.type.value.title(),
                    "Status": s.status.value if s.status.value != "TBD" else "TBC",
                }
            )

        import pandas as pd

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------


def fetch_data(series_id: str, season: int):
    """Fetch data for a series/season and store in session state."""
    with st.spinner("Fetching schedule from IndyCar.com…"):
        try:
            connector = None
            for series_desc in list_available_series():
                if series_desc.series_id == series_id:
                    connector = get_connector(series_desc.connector_id)
                    break

            if not connector:
                st.error(f"No connector found for series: {series_id}")
                return

            raw_payload = connector.fetch_season(series_id, season)
            events = connector.extract(raw_payload)
            events = connector.normalize(events)

            series_desc = next(
                s
                for s in connector.supported_series()
                if s.series_id == series_id
            )

            series = Series(
                series_id=series_id,
                name=series_desc.name,
                season=season,
                category=series_desc.category,
                events=events,
            )

            validator = DataValidator()
            validation_result = validator.validate_series(series)

            st.session_state.series = series
            st.session_state.original_series = series.model_copy(deep=True)
            st.session_state.validation_result = validation_result

            st.rerun()

        except Exception as e:
            st.error(f"Failed to fetch data: {str(e)}")
            import traceback

            st.code(traceback.format_exc())


def handle_upload(uploaded_file):
    """Handle uploaded JSON file."""
    try:
        content = uploaded_file.read().decode("utf-8")
        data = json.loads(content)

        if "manifest" in data and "series" in data:
            series_data = data["series"]
        else:
            series_data = data

        series = Series.from_dict(series_data)
        st.session_state.series = series
        st.session_state.original_series = series.model_copy(deep=True)

        validator = DataValidator()
        validation_result = validator.validate_series(series)
        st.session_state.validation_result = validation_result

        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Upload failed: {str(e)}")
