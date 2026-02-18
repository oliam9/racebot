"""
Step 1: Configuration & Source Selection
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from database.repository import Repository
from connectors import list_available_series, get_connector

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

    # Championship Selector
    # We want to match existing connectors to championships if possible, 
    # or just allow user to pick a target championship ID to map scraped data TO.
    
    # Create dropdown options from championships dataframe
    champ_options = {}
    # Create dropdown options from championships dataframe
    champ_options = {}
    if not championships_df.empty:
        # Sort alphabetically
        championships_df = championships_df.sort_values("name")
        for _, row in championships_df.iterrows():
            champ_options[row["name"]] = row["id"]
            
    selected_champ_name = st.selectbox(
        "Target Championship (Supabase)", 
        options=list(champ_options.keys()),
        help="Select the championship in the database to link events to."
    )
    selected_champ_id = champ_options.get(selected_champ_name)

    # Scraper Source Selector (from existing connectors)
    # Filter connectors that might match. For now, show all.
    connectors = list_available_series()
    # Sort connectors alphabetically
    connectors.sort(key=lambda x: x.name)
    connector_options = {s.name: s for s in connectors}
    selected_connector_name = st.selectbox(
        "Source Scraper", 
        options=list(connector_options.keys()),
        help="Which scraper logic to run."
    )
    selected_series_desc = connector_options.get(selected_connector_name)

    col1, col2 = st.columns(2)
    with col1:
        current_year = datetime.now().year
        season = st.number_input("Season", min_value=1950, max_value=current_year + 5, value=current_year)
    
    with col2:
        # Optional: Pre-select a default circuit if scraping a single-round event? 
        # Usually scraping a season yields multiple circuits. 
        # We'll handle circuit mapping in the Draft phase or allow a default here.
        # Requirements said: "Show a Circuit selector... allow 'no circuit'"
        circuit_options = {"(Detect from scrape / Mixed)": None}
        if not circuits_df.empty:
            for _, row in circuits_df.iterrows():
                label = f"{row['name']} ({row.get('location', {}).get('country', '')})" if 'country' in row else row['name']
                circuit_options[label] = row["id"]
        
        selected_circuit_label = st.selectbox(
            "Default Circuit (Optional)", 
            options=list(circuit_options.keys())
        )
        selected_circuit_id = circuit_options.get(selected_circuit_label)

    if st.button("Start Scraping 🚀", type="primary"):
        with st.spinner(f"Scraping {selected_connector_name} for season {season}..."):
            try:
                # 1. Run Scraper
                connector = get_connector(selected_series_desc.connector_id)
                raw_data = connector.fetch_season(selected_series_desc.series_id, season)
                scraped_events = connector.extract(raw_data)
                normalized_events = connector.normalize(scraped_events)
                
                # 2. Convert to Draft DataFrames expected by our DB Schema
                # We need to map the internal `models.schema.Event` to `models.db_schema.ChampionshipEvent` dicts
                
                draft_events = []
                draft_sessions = []
                
                # Helper for circuit matching
                def auto_match_circuit(evt_name, df_circuits):
                    if not evt_name or df_circuits.empty:
                        return None
                    
                    evt_lower = str(evt_name).lower()
                    
                    for _, row in df_circuits.iterrows():
                        c_id = row["id"]
                        c_name = str(row.get("name", "")).lower()
                        c_short = str(row.get("short_name", "")).lower()
                        c_city = str(row.get("city", "")).lower()
                        c_country = str(row.get("location", {}).get("country", "")).lower() if isinstance(row.get("location"), dict) else ""
                        
                        if c_city and c_city in evt_lower: return c_id
                        if c_short and (c_short == evt_lower or c_short in evt_lower or evt_lower in c_short): return c_id
                        if c_name and (c_name in evt_lower or evt_lower in c_name): return c_id
                        if c_country and c_country == evt_lower: return c_id
                             
                    return None
                
                for idx, evt in enumerate(normalized_events, start=1):
                    # Convert extracted event to DB definition
                    e_dict = {
                        "championship_id": selected_champ_id,
                        "circuit_id": selected_circuit_id, 
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
                    
                    # Auto-match circuit if not set
                    if e_dict["circuit_id"] is None and not circuits_df.empty:
                         match_id = auto_match_circuit(e_dict["name"], circuits_df)
                         if match_id:
                             e_dict["circuit_id"] = match_id

                    draft_events.append(e_dict)
                    
                    # LINKAGE
                    temp_evt_id = len(draft_events)
                    draft_events[-1]["temp_id"] = temp_evt_id
                    
                    # Sessions
                    for sess in evt.sessions:
                        s_dict = {
                            "temp_event_id": temp_evt_id, # Linkage
                            "name": sess.name,
                            "session_type": sess.type.value.lower(),
                            "start_time": sess.start,
                            "end_time": sess.end,
                            "is_cancelled": sess.status == "CANCELLED",
                            "id": None, 
                            "championship_event_id": None
                        }
                        draft_sessions.append(s_dict)

                # Store in session state
                st.session_state.draft_events = pd.DataFrame(draft_events)
                df_sessions = pd.DataFrame(draft_sessions)
                
                if not df_sessions.empty:
                    # Helper to split ISO string into Naive Local Time + Offset
                    import dateutil.parser
                    
                    def parse_local(iso_str):
                        if not iso_str: return None, None
                        try:
                            dt = dateutil.parser.parse(str(iso_str))
                            # Return Naive Datetime (Wall Time), Offset String (e.g. "+11:00")
                            offset_str = dt.strftime("%z")
                            # Insert colon in offset if needed (python %z is +1100, ISO often +11:00)
                            if offset_str and len(offset_str) == 5:
                                offset_str = offset_str[:3] + ":" + offset_str[3:]
                                
                            return dt.replace(tzinfo=None), offset_str
                        except:
                            return None, None

                    # Apply to start_time
                    s_parsed = df_sessions["start_time"].apply(parse_local)
                    df_sessions["start_time"] = s_parsed.apply(lambda x: x[0])
                    df_sessions["start_time_offset"] = s_parsed.apply(lambda x: x[1])
                    
                    # Apply to end_time
                    e_parsed = df_sessions["end_time"].apply(parse_local)
                    df_sessions["end_time"] = e_parsed.apply(lambda x: x[0])
                    df_sessions["end_time_offset"] = e_parsed.apply(lambda x: x[1])

                st.session_state.draft_sessions = df_sessions
                st.session_state.scraper_config = {
                    "championship_id": selected_champ_id,
                    "season": season,
                    "connector_id": selected_series_desc.connector_id
                }
                
                st.session_state.scraper_step = "draft"
                st.rerun()
                
            except Exception as e:
                st.error(f"Scraping failed: {e}")
                import traceback
                st.code(traceback.format_exc())
