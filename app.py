"""
Main Streamlit application — single-page layout.
"""

import streamlit as st
from ui import home
from models.enums import SessionType


# Page configuration
st.set_page_config(
    page_title="Motorsport Data Collector",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    /* Compact sidebar */
    [data-testid="stSidebar"] {
        min-width: 240px;
        max-width: 300px;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        font-size: 14px;
    }

    /* Larger touch targets for iOS */
    .stButton > button {
        min-height: 40px;
        font-size: 15px;
    }

    /* Tighter spacing */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1rem;
    }

    /* Prevent zoom on iOS input focus */
    input, select, textarea {
        font-size: 16px !important;
    }

    /* Nicer expander headers */
    .streamlit-expanderHeader {
        font-size: 16px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


def render_sidebar_stats(series):
    """Show season stats in the sidebar."""
    total_events = len(series.events)
    total_sessions = sum(len(e.sessions) for e in series.events)

    # Count session types
    race_count = 0
    practice_count = 0
    quali_count = 0
    other_count = 0
    for e in series.events:
        for s in e.sessions:
            if s.type == SessionType.RACE:
                race_count += 1
            elif s.type == SessionType.PRACTICE:
                practice_count += 1
            elif s.type == SessionType.QUALIFYING:
                quali_count += 1
            else:
                other_count += 1

    # Track types
    street_circuits = set()
    ovals = set()
    road_courses = set()
    for e in series.events:
        circuit = (e.venue.circuit or "").lower()
        if "street" in circuit:
            street_circuits.add(e.venue.circuit)
        elif any(kw in circuit for kw in ["speedway", "raceway", "mile", "oval"]):
            ovals.add(e.venue.circuit)
        elif e.venue.circuit:
            road_courses.add(e.venue.circuit)

    # Season span
    if series.events:
        first = series.events[0].start_date.strftime("%b %-d")
        last = series.events[-1].end_date.strftime("%b %-d")
        span = f"{first} → {last}"
    else:
        span = "—"

    # Unique tracks
    unique_tracks = set(
        e.venue.circuit for e in series.events if e.venue.circuit
    )

    st.markdown("---")
    st.markdown("#### 📊 Season Overview")

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Events", total_events)
        st.metric("Races", race_count)
    with col_b:
        st.metric("Sessions", total_sessions)
        st.metric("Tracks", len(unique_tracks))

    st.caption(f"📅 {span}")

    st.markdown("---")
    st.markdown("#### 🏟️ Track Types")
    if street_circuits:
        st.markdown(f"🏙️ Streets: **{len(street_circuits)}**")
    if ovals:
        st.markdown(f"🔵 Ovals: **{len(ovals)}**")
    if road_courses:
        st.markdown(f"🟢 Road: **{len(road_courses)}**")

    st.markdown("---")
    st.markdown("#### 📋 Sessions Breakdown")
    st.caption(
        f"🏎️ Races: {race_count} · "
        f"🔧 Practice: {practice_count}\n\n"
        f"⏱️ Qualifying: {quali_count} · "
        f"📌 Other: {other_count}"
    )


def main():
    """Main application entrypoint."""

    with st.sidebar:
        st.markdown("### 🏁 Racebot")

        uploaded_file = st.file_uploader(
            "📤 Upload JSON",
            type=["json"],
            key="json_uploader",
            label_visibility="collapsed",
        )
        if uploaded_file is not None:
            home.handle_upload(uploaded_file)

        # Show stats when data is loaded
        if "series" in st.session_state and st.session_state.series:
            render_sidebar_stats(st.session_state.series)

    # Main page
    home.render()


if __name__ == "__main__":
    main()

