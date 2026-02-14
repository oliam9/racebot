"""
Viewer for database content.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from database.repository import Repository

def render():
    st.header("👀 Database Viewer")
    
    repo = Repository()
    
    # Select Championship
    try:
        championships_df = repo.get_championships()
        circuits_df = repo.get_circuits()
    except Exception as e:
        st.error(f"Failed to load reference data: {e}")
        return

    # Sort championships alphabetically
    champ_options = {}
    if not championships_df.empty:
        championships_df = championships_df.sort_values("name")
        for _, row in championships_df.iterrows():
            champ_options[row["name"]] = row["id"]

    col1, col2 = st.columns(2)
    with col1:
        selected_champ_name = st.selectbox(
            "Select Championship", 
            options=list(champ_options.keys())
        )
        selected_champ_id = champ_options.get(selected_champ_name)
    
    with col2:
        current_year = datetime.now().year
        season = st.number_input("Season", min_value=1950, max_value=current_year + 5, value=current_year, key="view_season")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Load Data", type="primary", key="view_load_btn"):
            if selected_champ_id:
                try:
                    with st.spinner("Fetching data..."):
                        e_df, s_df = repo.get_events(selected_champ_id, season)
                        
                        # Post-process events
                        if not e_df.empty:
                            if not circuits_df.empty and "circuit_id" in e_df.columns:
                                circuit_map = dict(zip(circuits_df["id"], circuits_df["name"]))
                                e_df["circuit_name"] = e_df["circuit_id"].map(circuit_map)
                            
                            if "round_number" in e_df.columns:
                                e_df = e_df.sort_values("round_number")
                        
                        st.session_state.view_data = {
                            "events": e_df,
                            "sessions": s_df,
                            "params": (selected_champ_id, season)
                        }
                except Exception as e:
                     st.error(f"Error fetching data: {e}")
            else:
                st.warning("Please select a championship.")

    st.markdown("---")

    # Display Logic
    if "view_data" in st.session_state:
        saved_data = st.session_state.view_data
        # Check if params match current selection
        if saved_data["params"] == (selected_champ_id, season):
            events_df = saved_data["events"]
            sessions_df = saved_data["sessions"]
            
            if events_df.empty:
                st.info(f"No events found for {selected_champ_name} in {season}.")
            else:
                st.subheader(f"{selected_champ_name} - {season} Schedule")
                
                for _, event in events_df.iterrows():
                    # Get sessions for this event
                    e_sessions = sessions_df[sessions_df["championship_event_id"] == event["id"]] if not sessions_df.empty else pd.DataFrame()
                    
                    circuit_str = event.get("circuit_name", event.get("circuit_id", "Unknown Circuit"))
                    confirmed_icon = "✅" if event.get("is_confirmed") else "⚠️"
                    
                    with st.expander(f"Round {event.get('round_number', '?')}: {event['name']} ({circuit_str}) {confirmed_icon}"):
                        c1, c2 = st.columns(2)
                        c1.write(f"**Dates:** {event.get('start_date')} - {event.get('end_date')}")
                        c1.write(f"**Circuit ID:** `{event.get('circuit_id')}`")
                        c1.write(f"**Event ID:** `{event['id']}`")
                        
                        if not e_sessions.empty:
                            e_sessions = e_sessions.sort_values("start_time")
                            st.dataframe(
                                e_sessions[["session_type", "name", "start_time", "end_time", "is_cancelled"]],
                                width="stretch",
                                hide_index=True
                            )
                        else:
                            st.info("No sessions found.")
        else:
             st.info("Click 'Load Data' to view schedule for the selected parameters.")
