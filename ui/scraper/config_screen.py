"""
Step 1: Configuration — select championship & season, then scrape.

The connector is auto-detected from the championship name by matching
against all registered connector series names.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from database.repository import Repository
from connectors import list_available_series, get_connector


def _match_connector(champ_name: str):
    """Auto-detect the best connector for a championship name.

    Matches by checking if the championship name contains (or is contained in)
    a registered series name, using case-insensitive substring matching.
    Returns (SeriesDescriptor, confidence_label) or (None, None).
    """
    if not champ_name:
        return None, None

    connectors = list_available_series()
    champ_lower = champ_name.lower()

    # Pass 1: exact-ish match (champ name contains series name or vice versa)
    best = None
    best_score = 0
    for s in connectors:
        s_lower = s.name.lower()
        if s_lower == champ_lower:
            return s, "exact"
        # Prefer longer matching substrings
        if s_lower in champ_lower or champ_lower in s_lower:
            score = len(s_lower)
            if score > best_score:
                best = s
                best_score = score

    if best:
        return best, "auto"

    # Pass 2: keyword overlap
    champ_words = set(champ_lower.split())
    for s in connectors:
        s_words = set(s.name.lower().split())
        overlap = champ_words & s_words - {"championship", "series", "the", "fia", "world"}
        if len(overlap) >= 2:
            return s, "fuzzy"

    return None, None


def render():
    st.subheader("1. Configuration")

    repo = Repository()

    # Load reference data
    try:
        championships_df = repo.get_championships()
        circuits_df = repo.get_circuits()
    except Exception as e:
        st.error(f"Failed to load reference data: {e}")
        return

    # ── Championship selector ────────────────────────────────────
    champ_options = {}
    if not championships_df.empty:
        championships_df = championships_df.sort_values("name")
        for _, row in championships_df.iterrows():
            champ_options[row["name"]] = row["id"]

    selected_champ_name = st.selectbox(
        "Championship",
        options=list(champ_options.keys()),
        help="Select the championship to scrape and link events to.",
    )
    selected_champ_id = champ_options.get(selected_champ_name)

    # ── Auto-detect connector ────────────────────────────────────
    matched_series, match_type = _match_connector(selected_champ_name)

    if matched_series:
        icon = "🟢" if match_type in ("exact", "auto") else "🟡"
        st.caption(f"{icon} Connector: **{matched_series.name}** (`{matched_series.connector_id}`)")
    else:
        st.warning("⚠️ No matching connector found for this championship. "
                   "Use the **AI Scrapper** tab instead.")

    # ── Season ───────────────────────────────────────────────────
    current_year = datetime.now().year
    season = st.number_input(
        "Season", min_value=1950, max_value=current_year + 5, value=current_year
    )

    # ── Scrape button ────────────────────────────────────────────
    if st.button("🚀 Start Scraping", type="primary", use_container_width=True,
                 disabled=matched_series is None):
        with st.spinner(f"Scraping {matched_series.name} for season {season}..."):
            try:
                connector = get_connector(matched_series.connector_id)
                raw_data = connector.fetch_season(matched_series.series_id, season)
                scraped_events = connector.extract(raw_data)
                normalized_events = connector.normalize(scraped_events)

                # ── Build draft DataFrames ────────────────────────
                draft_events = []
                draft_sessions = []

                def auto_match_circuit(evt_name, df_circuits):
                    if not evt_name or df_circuits.empty:
                        return None
                    evt_lower = str(evt_name).lower()
                    for _, row in df_circuits.iterrows():
                        c_id = row["id"]
                        c_name = str(row.get("name", "")).lower()
                        c_short = str(row.get("short_name", "")).lower()
                        c_city = str(row.get("city", "")).lower()
                        c_country = (
                            str(row.get("location", {}).get("country", "")).lower()
                            if isinstance(row.get("location"), dict) else ""
                        )
                        if c_city and c_city in evt_lower: return c_id
                        if c_short and (c_short == evt_lower or c_short in evt_lower or evt_lower in c_short): return c_id
                        if c_name and (c_name in evt_lower or evt_lower in c_name): return c_id
                        if c_country and c_country == evt_lower: return c_id
                    return None

                for idx, evt in enumerate(normalized_events, start=1):
                    e_dict = {
                        "championship_id": selected_champ_id,
                        "circuit_id": None,
                        "name": evt.name,
                        "round_number": idx,
                        "season": season,
                        "start_date": evt.start_date,
                        "end_date": evt.end_date,
                        "is_confirmed": True,
                        "is_cancelled": False,
                        "metadata": {},
                        "id": None,
                    }

                    # Auto-match circuit
                    if not circuits_df.empty:
                        match_id = auto_match_circuit(e_dict["name"], circuits_df)
                        if match_id:
                            e_dict["circuit_id"] = match_id

                    draft_events.append(e_dict)

                    temp_evt_id = len(draft_events)
                    draft_events[-1]["temp_id"] = temp_evt_id

                    for sess in evt.sessions:
                        s_dict = {
                            "temp_event_id": temp_evt_id,
                            "name": sess.name,
                            "session_type": sess.type.value.lower(),
                            "start_time": sess.start,
                            "end_time": sess.end,
                            "is_cancelled": sess.status == "CANCELLED",
                            "id": None,
                            "championship_event_id": None,
                        }
                        draft_sessions.append(s_dict)

                st.session_state.draft_events = pd.DataFrame(draft_events)
                df_sessions = pd.DataFrame(draft_sessions)

                if not df_sessions.empty:
                    import dateutil.parser

                    def parse_local(iso_str):
                        if not iso_str:
                            return None, None
                        try:
                            dt = dateutil.parser.parse(str(iso_str))
                            offset_str = dt.strftime("%z")
                            if offset_str and len(offset_str) == 5:
                                offset_str = offset_str[:3] + ":" + offset_str[3:]
                            return dt.replace(tzinfo=None), offset_str
                        except Exception:
                            return None, None

                    s_parsed = df_sessions["start_time"].apply(parse_local)
                    df_sessions["start_time"] = s_parsed.apply(lambda x: x[0])
                    df_sessions["start_time_offset"] = s_parsed.apply(lambda x: x[1])

                    e_parsed = df_sessions["end_time"].apply(parse_local)
                    df_sessions["end_time"] = e_parsed.apply(lambda x: x[0])
                    df_sessions["end_time_offset"] = e_parsed.apply(lambda x: x[1])

                st.session_state.draft_sessions = df_sessions
                st.session_state.scraper_config = {
                    "championship_id": selected_champ_id,
                    "season": season,
                    "connector_id": matched_series.connector_id,
                }

                st.session_state.scraper_step = "draft"
                st.rerun()

            except Exception as e:
                st.error(f"Scraping failed: {e}")
                import traceback
                st.code(traceback.format_exc())
