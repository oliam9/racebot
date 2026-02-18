"""
Step 2: Scrape Results (Draft Tables) & Validation
"""

import streamlit as st
import pandas as pd
from models.db_schema import SessionType, ChampionshipCategory

def render():
    st.subheader("2. Review & Edit Drafts")
    
    if "draft_events" not in st.session_state or "draft_sessions" not in st.session_state:
        st.error("No draft data found. Please go back to configuration.")
        return

    # Ensure datetimes are actual datetime objects (fixes StreamlitAPIException)
    if not st.session_state.draft_sessions.empty:
        for col in ["start_time", "end_time"]:
            if col in st.session_state.draft_sessions.columns:
                st.session_state.draft_sessions[col] = pd.to_datetime(
                    st.session_state.draft_sessions[col], errors="coerce"
                )


    # Load reference data for Circuit Selector
    from database.repository import Repository
    repo = Repository()
    circuits_df = repo.get_circuits()
    
    # Create Circuit Map: Name -> ID and ID -> Name
    circuit_map = {}
    circuit_id_to_name = {}
    circuit_options = []
    
    if not circuits_df.empty:
        # Sort by name for better UX - ALPHABETICALLY
        circuits_df = circuits_df.sort_values("name")
        for _, row in circuits_df.iterrows():
            c_name = f"{row['name']} ({row.get('location', {}).get('country', '')})" if 'location' in row else row['name']
            circuit_map[c_name] = row["id"]
            circuit_id_to_name[row["id"]] = c_name
            circuit_options.append(c_name)
    
    # Sort options list specifically just in case (though df sort usually enough)
    circuit_options.sort()

    # Prepare Events Dataframe with Circuit Names
    df_events = st.session_state.draft_events.copy()
    
    # If we have circuit_ids, try to map them to names for the dropdown
    if "circuit_name" not in df_events.columns:
        df_events["circuit_name"] = df_events["circuit_id"].map(circuit_id_to_name)

    # --- Events Editor ---
    st.markdown("### 📅 Events")
    
    # Configure columns for editor
    event_column_config = {
        "championship_id": st.column_config.TextColumn(disabled=True),
        "temp_id": st.column_config.NumberColumn(disabled=True, help="Temporary ID for linking sessions"),
        # Hide raw ID by omitting from column_order, but keep config just in case
        "circuit_id": st.column_config.TextColumn(disabled=True), 
        "circuit_name": st.column_config.SelectboxColumn(
            "Circuit",
            options=circuit_options,
            required=False,
            width="medium",
            help="Select the circuit from the database"
        ),
        "start_date": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "end_date": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "round_number": st.column_config.NumberColumn(min_value=0, max_value=100, step=1),
        "metadata": st.column_config.TextColumn() 
    }
    
    # order columns to put circuit_name near start
    column_order = ["round_number", "circuit_name", "name", "start_date", "end_date", "is_confirmed", "circuit_id", "temp_id", "championship_id", "metadata"]
    
    edited_events = st.data_editor(
        df_events,
        column_config=event_column_config,
        column_order=[c for c in column_order if c in df_events.columns],
        num_rows="dynamic",
        width="stretch",
        key="editor_events"
    )
    
    # --- Sync Circuit ID ---
    # When user changes circuit_name, we must update circuit_id immediately for the UI state
    # so that if they click "Stage", it has the right IDs.
    if not edited_events.empty and "circuit_name" in edited_events.columns:
        # Map names back to IDs using the map created earlier
        edited_events["circuit_id"] = edited_events["circuit_name"].map(circuit_map)
    
    # --- Sessions Editor ---
    st.markdown("### ⏱️ Sessions")
    
    session_column_config = {
        "temp_event_id": st.column_config.NumberColumn(help="Link to Event temp_id"),
        "session_type": st.column_config.SelectboxColumn(
            options=[t.value for t in SessionType],
            required=True
        ),
        "start_time": st.column_config.DatetimeColumn(format="D MMM YYYY, HH:mm"),
        "end_time": st.column_config.DatetimeColumn(format="D MMM YYYY, HH:mm"),
    }
    
    edited_sessions = st.data_editor(
        st.session_state.draft_sessions,
        column_config=session_column_config,
        num_rows="dynamic",
        width="stretch",
        column_order=["temp_event_id", "session_type", "name", "start_time", "end_time", "is_cancelled"],
        key="editor_sessions"
    )
    
    # --- Sync Circuit ID ---
    # When user changes circuit_name, update circuit_id and rerun to reflect changes
    # Use simpler logic: if map output differs from current column, update.
    if not edited_events.empty and "circuit_name" in edited_events.columns:
        # Calculate expected IDs
        expected_ids = edited_events["circuit_name"].map(circuit_map)
        
        # We enforce the update on the session state
        edited_events["circuit_id"] = expected_ids
        
        # Only rerun if the data actually changed from what is currently in session_state
        # This prevents infinite loops if data_editor triggers rerun, we update, trigger rerun...
        # We compare against st.session_state.draft_events which holds the "previous" stable state
        
        # For now, just save it. The "Stage" button logic remaps it anyway, so it's safe.
        st.session_state.draft_events = edited_events
        st.session_state.draft_sessions = edited_sessions

    # --- Validation ---
    st.markdown("---")
    st.markdown("#### 🛡️ Validation Report")
    
    errors = []
    
    # Validate Events
    if edited_events.empty:
        errors.append("❌ No events to stage.")
    else:
        # Check unique rounds
        if edited_events["round_number"].duplicated().any():
            dupes = edited_events.loc[edited_events["round_number"].duplicated(), "round_number"].tolist()
            if any(d > 0 for d in dupes):
                errors.append(f"⚠️ Duplicate round numbers detected: {dupes}")
        
        # Check required fields
        if edited_events["name"].isnull().any() or (edited_events["name"] == "").any():
            errors.append("❌ Missing event names.")

        # Check for missing circuit IDs (unmapped)
        if edited_events["circuit_id"].isnull().any():
             errors.append("❌ Some events have no circuit selected.")

    # Validate Sessions
    valid_temp_ids = set(edited_events["temp_id"].unique())
    orphans = edited_sessions[~edited_sessions["temp_event_id"].isin(valid_temp_ids)]
    if not orphans.empty:
        errors.append(f"❌ {len(orphans)} sessions have invalid 'temp_event_id' (no matching event).")

    if errors:
        for err in errors:
            if "❌" in err:
                st.error(err)
            else:
                st.warning(err)
        
        can_proceed = not any("❌" in e for e in errors)
    else:
        st.success("✅ All checks passed.")
        can_proceed = True

    # --- Actions ---
    col_l, col_r = st.columns([1, 4])
    with col_l:
        if st.button("⬅️ Back"):
            st.session_state.scraper_step = "config"
            st.rerun()
            
    with col_r:
        if st.button("Stage to Supabase ➡️", type="primary", disabled=not can_proceed):
            # Map circuit_name back to circuit_id
            # We iterate over edited_events and look up ID from name
            final_events = edited_events.copy()
            final_events["circuit_id"] = final_events["circuit_name"].map(circuit_map)
            
            # Warn if any mapping failed
            if final_events["circuit_id"].isnull().any():
                st.error("❌ Some circuits could not be mapped to an ID. Please select valid circuits.")
                return

            # Save state
            st.session_state.draft_events = final_events
            st.session_state.draft_sessions = edited_sessions
            
            # Transition
            st.session_state.scraper_step = "staging"
            st.rerun()
