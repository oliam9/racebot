"""
AI Scrapper tab — smart web scraping for any motorsport site.

Four-tier strategy:
  1. Inline JSON — __NEXT_DATA__, embedded scripts (F1/F2/F3 Next.js)
  2. Network capture — intercept XHR/fetch API responses
  3. AI single-page — Gemini reads the HTML
  4. AI two-phase — calendar page → event detail pages
"""

import streamlit as st
import pandas as pd
from datetime import datetime


def render():
    # If draft data exists, show the draft review screen
    if (st.session_state.get("scraper_step") == "draft"
            and "draft_events" in st.session_state):
        from ui.scraper.draft_screen import render as render_draft
        st.header("🤖 AI Scrapper — Review Results")
        if st.button("← Back to scraper", key="ai_back"):
            st.session_state.scraper_step = None
            st.rerun()
        render_draft()
        return

    st.header("🤖 AI Scrapper")

    st.markdown("""
    Paste any motorsport schedule URL and let AI extract the full calendar
    with session details — no custom connector needed.
    """)

    # ── Championship selector ────────────────────────────────────────
    from database.repository import Repository
    repo = Repository()

    try:
        championships_df = repo.get_championships()
        circuits_df = repo.get_circuits()
    except Exception as e:
        st.error(f"Failed to load reference data: {e}")
        return

    champ_options = {}
    if not championships_df.empty:
        championships_df = championships_df.sort_values("name")
        for _, row in championships_df.iterrows():
            champ_options[row["name"]] = row["id"]

    selected_champ_name = st.selectbox(
        "Target Championship",
        options=list(champ_options.keys()),
        help="The championship in the database to link events to.",
    )
    selected_champ_id = champ_options.get(selected_champ_name)

    # ── URL input ────────────────────────────────────────────────────
    target_url = st.text_input(
        "🔗 Schedule Page URL",
        placeholder="https://www.motogp.com/en/calendar",
        help="Paste the URL of the championship's calendar / schedule page.",
    )

    # ── Season ───────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        current_year = datetime.now().year
        season = st.number_input(
            "Season", min_value=1950, max_value=current_year + 5, value=current_year
        )
    with col2:
        series_name = st.text_input(
            "Series Name (for AI)",
            value=selected_champ_name or "",
            help="Name the AI will use to understand what series to extract.",
        )

    upcoming_only = st.checkbox(
        "📅 Upcoming events only",
        value=True,
        help="Filter out past events that already have results.",
    )

    # ── Scrape button ────────────────────────────────────────────────
    if st.button("🚀 Start AI Scraping", type="primary", use_container_width=True):
        if not target_url:
            st.error("Please enter a schedule page URL.")
            return

        # Progress container
        progress_area = st.empty()
        status_text = st.empty()

        def update_progress(msg):
            status_text.markdown(f"*{msg}*")

        try:
            from connectors.dynamic_connector import DynamicAIConnector

            connector = DynamicAIConnector()
            connector.set_target_url(target_url)
            connector.set_upcoming_only(upcoming_only)
            connector.set_progress_callback(update_progress)

            # Phase 1 + 2: Fetch and extract
            with st.spinner("🤖 AI is scraping... this may take a few minutes for large calendars."):
                raw_data = connector.fetch_season("custom", season)
                scraped_events = connector.extract(raw_data)
                normalized_events = connector.normalize(scraped_events)

            status_text.empty()

            if not normalized_events:
                st.warning("⚠️ No events were extracted. Try a different URL or check the page content.")
                return

            st.success(f"✅ Extracted **{len(normalized_events)}** events!")

            # ── Build draft DataFrames ───────────────────────────────
            draft_events = []
            draft_sessions = []

            # Circuit matching helper
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
                    if c_short and (c_short == evt_lower or c_short in evt_lower): return c_id
                    if c_name and (c_name in evt_lower or evt_lower in c_name): return c_id
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
                    match_id = auto_match_circuit(evt.name, circuits_df)
                    if match_id:
                        e_dict["circuit_id"] = match_id

                draft_events.append(e_dict)

                # Linkage
                temp_evt_id = len(draft_events)
                draft_events[-1]["temp_id"] = temp_evt_id

                # Sessions
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

            # Store in session state (same format as connector scraper)
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
                "connector_id": "dynamic_ai",
            }

            # Transition to draft review (reuse the existing scraper draft screen)
            st.session_state.scraper_step = "draft"
            st.rerun()

        except Exception as e:
            st.error(f"❌ Scraping failed: {e}")
            import traceback
            st.code(traceback.format_exc())

    # ── Show extraction info ─────────────────────────────────────────
    with st.expander("ℹ️ How it works"):
        st.markdown("""
        **Tier 1 — Inline JSON** (instant)
        - Checks for embedded data (`__NEXT_DATA__`, inline scripts)
        - Works for Next.js sites (F1, F2, F3) — no AI needed

        **Tier 2 — Network capture** (fast)
        - Uses Playwright to load the page and intercept API responses
        - Works for SPAs that load data via XHR/fetch

        **Tier 3 — AI single-page** (slower)
        - Gemini AI reads the HTML and extracts schedule data

        **Tier 4 — AI two-phase** (slowest)
        - AI extracts calendar, then visits each event page for sessions

        **Auto session enrichment**: If events are found without sessions
        but have detail page URLs, the scraper visits those pages to get
        session data automatically.
        """)
