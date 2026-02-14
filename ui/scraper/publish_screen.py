"""
Step 4: Publish to Production
"""

import streamlit as st
from database.repository import Repository

def render():
    st.subheader("4. Publishing...")
    
    repo = Repository()
    
    if "publish_result" not in st.session_state:
        with st.spinner("Upserting data to production tables..."):
            try:
                # 1. Get staged data (or use what we have in memory for Draft->Prod logic)
                # The data models in `st.session_state.staged_events` match `stg_` table columns.
                # However, our repository `publish_events` expects list of dicts.
                
                if "staged_events" in st.session_state and not st.session_state.staged_events.empty:
                    events_payload = st.session_state.staged_events.to_dict(orient="records")
                    sessions_payload = st.session_state.staged_sessions.to_dict(orient="records")
                else:
                    # Fallback to draft if staging read failed
                    events_payload = st.session_state.draft_events.to_dict(orient="records")
                    sessions_payload = st.session_state.draft_sessions.to_dict(orient="records")

                # 2. Publish Events
                # Returns map of (season, round) -> event_id
                event_map = repo.publish_events(events_payload)
                
                # 3. Enhance sessions with parent event linkage
                # We used `temp_id` in draft. We need to bridge `temp_id` -> `round_number` -> `event_id`
                # Assuming `draft_events` preserved order or we can lookup by round.
                
                # Create a map: temp_id -> (season, round)
                temp_id_map = {}
                for evt in events_payload:
                    t_id = evt.get("temp_id")
                    if t_id:
                        temp_id_map[t_id] = (evt["season"], evt["round_number"])
                
                # Augment sessions
                ready_sessions = []
                for sess in sessions_payload:
                    temp_id = sess.get("temp_event_id")
                    if temp_id in temp_id_map:
                        _, round_num = temp_id_map[temp_id]
                        sess["parent_round"] = round_num
                        ready_sessions.append(sess)
                
                config_season = st.session_state.scraper_config["season"]
                
                # 4. Publish Sessions
                s_ins, s_upd = repo.publish_sessions(ready_sessions, event_map, config_season)
                
                st.session_state.publish_result = {
                    "events_processed": len(event_map),
                    "sessions_inserted": s_ins,
                    "sessions_updated": s_upd
                }
                
            except Exception as e:
                st.error(f"Publish failed: {e}")
                import traceback
                st.code(traceback.format_exc())
                return

    # Show Summary
    res = st.session_state.publish_result
    st.success("🎉 Publish Complete!")
    
    st.markdown(f"""
    - **Events Upserted**: {res['events_processed']}
    - **Sessions Inserted**: {res['sessions_inserted']}
    - **Sessions Updated**: {res['sessions_updated']}
    """)
    
    if st.button("Start New Import"):
        # Clear all
        for key in list(st.session_state.keys()):
            if key.startswith("scraper_") or key in ["draft_events", "draft_sessions", "import_id", "staged_events", "staged_sessions", "publish_result"]:
                del st.session_state[key]
        st.session_state.scraper_step = "config"
        st.rerun()
