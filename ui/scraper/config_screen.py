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
                
                for evt in normalized_events:
                    # Convert extracted event to DB definition
                    # Start/End date might need adjustment if they are datetime objects
                    
                    e_dict = {
                        "championship_id": selected_champ_id,
                        "circuit_id": selected_circuit_id, # Default, can be overridden per row if we implemented circuit matching logic
                        "name": evt.name,
                        "round_number": 0, # Scraper needs to provide this or we generate it?
                        "season": season,
                        "start_date": evt.start_date,
                        "end_date": evt.end_date,
                        "is_confirmed": True, # Assumption
                        "is_cancelled": False,
                        "metadata": {}, # Could store original source URL etc
                        "id": None, # Ensure ID is None so DB generates it
                    }
                    
                    # Try to match circuit by name if not provided globally?
                    # For now keep simple: usage of global selector or manual edit in next step.
                    
                    draft_events.append(e_dict)
                    
                    # Sessions
                    # We need a way to link sessions to this event in the draft.
                    # We can use a temporary ID or just index.
                    # Let's use 'temp_id' for UI linkage
                    temp_evt_id = len(draft_events) # 1-based index as int ID for now
                    draft_events[-1]["temp_id"] = temp_evt_id
                    
                    for sess in evt.sessions:
                        s_dict = {
                            "temp_event_id": temp_evt_id, # Linkage
                            "name": sess.name,
                            "session_type": sess.type.value.lower(), # Enum mapping needs care
                            "start_time": sess.start, # ISO string? needs datetime
                            "end_time": sess.end,
                            "is_cancelled": sess.status == "CANCELLED",
                            "id": None, # Ensure ID is None
                            "championship_event_id": None # Linked via temp_id for now
                        }
                        draft_sessions.append(s_dict)

                # Store in session state
                st.session_state.draft_events = pd.DataFrame(draft_events)
                df_sessions = pd.DataFrame(draft_sessions)
                if not df_sessions.empty:
                    # Ensure datetime objects for editor compatibility
                    df_sessions["start_time"] = pd.to_datetime(df_sessions["start_time"], errors="coerce")
                    df_sessions["end_time"] = pd.to_datetime(df_sessions["end_time"], errors="coerce")
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
