"""
Step 4: Publish to Production
"""

import streamlit as st
import pandas as pd
from database.repository import Repository

def render():
    st.subheader("4. Publish to Production")
    
    if "staged_events" not in st.session_state or "staged_sessions" not in st.session_state:
        st.error("No staged data found. Please go back to staging.")
        if st.button("⬅️ Back to Staging"):
            st.session_state.scraper_step = "staging"
            st.rerun()
        return

    staged_events_df = st.session_state.staged_events
    staged_sessions_df = st.session_state.staged_sessions
    
    config = st.session_state.get("scraper_config", {})
    season = config.get("season")
    
    st.info(f"Ready to publish {len(staged_events_df)} events and {len(staged_sessions_df)} sessions to production.")
    
    with st.expander("Review Data to be Published"):
        st.write("Events:", staged_events_df)
        st.write("Sessions:", staged_sessions_df)

    if st.button("🚀 Confirm & Publish", type="primary"):
        repo = Repository()
        
        try:
            with st.spinner("Upserting Events..."):
                # 1. Publish Events & Get IDs
                # Convert DF to list of dicts
                events_data = staged_events_df.to_dict(orient="records")
                
                # repo.publish_events returns map: (season, round) -> event_id
                event_map = repo.publish_events(events_data)
                
                st.success(f"✅ Processed {len(events_data)} events.")
                
            with st.spinner("Linking & Upserting Sessions..."):
                # 2. Prepare Sessions
                # We need to map 'temp_event_id' in sessions to 'round_number' in events
                # so we can use event_map to find the real UUID.
                
                # Create map: temp_id -> round_number from staged_events
                # Ensure types match (int vs int)
                temp_id_to_round = dict(zip(staged_events_df["temp_id"], staged_events_df["round_number"]))
                
                sessions_data = staged_sessions_df.to_dict(orient="records")
                
                # Enrich sessions with parent_round
                valid_sessions = []
                for sess in sessions_data:
                    t_id = sess.get("temp_event_id")
                    if t_id in temp_id_to_round:
                        sess["parent_round"] = temp_id_to_round[t_id]
                        valid_sessions.append(sess)
                    else:
                        st.warning(f"⚠️ Skipping session '{sess.get('name')}' - could not link to an event (temp_id {t_id}).")
                
                # 3. Publish Sessions
                cnt_ins, cnt_upd = repo.publish_sessions(valid_sessions, event_map, season)
                
                st.success(f"✅ Processed {len(valid_sessions)} sessions (Inserted: {cnt_ins}, Updated: {cnt_upd}).")
                
            st.balloons()
            st.success("🎉 Publishing complete!")
            
            # Clear state button
            if st.button("Start New Import"):
                repo.clear_staging(st.session_state.import_id)
                for key in list(st.session_state.keys()):
                    if key.startswith("scraper_") or key in ["draft_events", "draft_sessions", "import_id", "staged_events", "staged_sessions"]:
                        del st.session_state[key]
                st.session_state.scraper_step = "config"
                st.rerun()
                
        except Exception as e:
            st.error(f"Publishing failed: {e}")
            st.exception(e)
