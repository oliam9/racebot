"""
Step 3: Staging (Second Verification)
"""

import streamlit as st
import pandas as pd
from database.repository import Repository

def render():
    st.subheader("3. Staging")
    
    repo = Repository()
    
    # 1. Perform Staging (Idempotent-ish check)
    if "import_id" not in st.session_state:
        with st.spinner("Writing to staging tables..."):
            try:
                import_id = repo.stage_data(
                    st.session_state.draft_events,
                    st.session_state.draft_sessions
                )
                st.session_state.import_id = import_id
                st.success(f"Successfully staged data! Import ID: `{import_id}`")
            except Exception as e:
                st.error(f"Staging failed: {e}")
                if st.button("Retry"):
                    st.rerun()
                return

    # 2. Read back
    if "staged_events" not in st.session_state:
        e_df, s_df = repo.get_staged_data(st.session_state.import_id)
        st.session_state.staged_events = e_df
        st.session_state.staged_sessions = s_df

    st.info("These rows are now in the Supabase `stg_` tables. Review one last time before publishing to production.")

    st.markdown("### 📤 Staged Events")
    st.dataframe(st.session_state.staged_events, width="stretch")
    
    st.markdown("### 📤 Staged Sessions")
    st.dataframe(st.session_state.staged_sessions, width="stretch")

    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("⬅️ Edit Draft"):
            # Go back to draft (keep import_id? No, maybe clear staging if we go back?)
            # For simplicity, we just navigate back. User can re-stage (creates new import_id).
            del st.session_state.import_id
            if "staged_events" in st.session_state: del st.session_state.staged_events
            if "staged_sessions" in st.session_state: del st.session_state.staged_sessions
            
            st.session_state.scraper_step = "draft"
            st.rerun()
            
    with col2:
        if st.button("🗑️ Clear & Abort"):
            repo.clear_staging(st.session_state.import_id)
            # Reset everything
            for key in list(st.session_state.keys()):
                if key.startswith("scraper_") or key in ["draft_events", "draft_sessions", "import_id", "staged_events", "staged_sessions"]:
                    try:
                        del st.session_state[key]
                    except KeyError:
                        pass
            st.session_state.scraper_step = "config"
            st.rerun()

    with col3:
        if st.button("🚀 Publish to Production", type="primary"):
            st.session_state.scraper_step = "publish"
            st.rerun()
