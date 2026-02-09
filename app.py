"""
Main Streamlit application entry point.
"""

import streamlit as st
from ui import home, review, export


# Page configuration
st.set_page_config(
    page_title="Motorsport Data Collector",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for iOS Safari optimization
st.markdown("""
<style>
    /* Larger touch targets for iOS */
    .stButton > button {
        min-height: 44px;
        font-size: 16px;
    }
    
    .stSelectbox, .stTextInput {
        font-size: 16px;
    }
    
    /* Better spacing for mobile */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Prevent zoom on iOS input focus */
    input, select, textarea {
        font-size: 16px !important;
    }
</style>
""", unsafe_allow_html=True)


def main():
    """Main application entrypoint."""
    
    # Sidebar navigation
    with st.sidebar:
        st.title("🏁 Navigation")
        
        page = st.radio(
            "Select Page",
            options=["Home", "Review & Edit", "Export"],
            key="navigation"
        )
        
        st.divider()
        
        # Show status in sidebar
        if "series" in st.session_state and st.session_state.series:
            series = st.session_state.series
            st.success("✅ Data Loaded")
            st.markdown(f"**Series:** {series.name}")
            st.markdown(f"**Season:** {series.season}")
            st.markdown(f"**Events:** {len(series.events)}")
            
            if "validation_result" in st.session_state:
                result = st.session_state.validation_result
                if result.is_valid:
                    st.success(f"✅ Valid ({len(result.warnings)} warnings)")
                else:
                    st.error(f"❌ {len(result.errors)} errors")
        else:
            st.info("No data loaded")
        
        st.divider()
        
        # About section
        with st.expander("ℹ️ About"):
            st.markdown("""
            **Motorsport Data Collector**
            
            A tool for collecting, editing, and exporting
            motorsport schedule data with full provenance
            tracking and validation.
            
            Built with Streamlit and Python.
            """)
    
    # Render selected page
    if page == "Home":
        home.render()
    elif page == "Review & Edit":
        review.render()
    elif page == "Export":
        export.render()


if __name__ == "__main__":
    main()
