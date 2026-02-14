"""
Main controller for the Scraper -> Supabase workflow.
Manages session state and navigation between wizard steps.
"""

import streamlit as st
from ui.scraper import config_screen, draft_screen, staging_screen, publish_screen

def render():
    st.header("🕷️ Scraper & Import Tool")
    
    # Initialize workflow state
    if "scraper_step" not in st.session_state:
        st.session_state.scraper_step = "config"
    
    # Step wizard navigation (read-only indicator)
    steps = ["config", "draft", "staging", "publish"]
    current_idx = steps.index(st.session_state.scraper_step)
    
    st.progress( (current_idx + 1) / len(steps) )
    
    # Conditional rendering
    if st.session_state.scraper_step == "config":
        config_screen.render()
        
    elif st.session_state.scraper_step == "draft":
        draft_screen.render()
        
    elif st.session_state.scraper_step == "staging":
        staging_screen.render()
        
    elif st.session_state.scraper_step == "publish":
        publish_screen.render()
    
    # Sidebar reset
    with st.sidebar:
        st.markdown("---")
        if st.button("🔄 Reset Scraper Process", type="secondary"):
            for key in list(st.session_state.keys()):
                if key.startswith("scraper_") or key in ["draft_events", "draft_sessions", "import_id"]:
                    del st.session_state[key]
            st.session_state.scraper_step = "config"
            st.rerun()
