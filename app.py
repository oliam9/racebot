"""
Main Streamlit application — modern segmented navigation.
"""

import os
import streamlit as st
from ui import home
from ui import search_fallback
from ui import home
from ui import search_fallback
from ui import scraper
from ui import view  # New import
from models.enums import SessionType

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

from utils import auth  # Supabase Auth



# Page configuration
st.set_page_config(
    page_title="MotorsportBot",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    /* ── Sidebar ─────────────────────────────── */
    [data-testid="stSidebar"] {
        min-width: 240px;
        max-width: 280px;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        font-size: 13px;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 0rem;
        padding-bottom: 3.5rem;
    }

    /* Tight centered title */
    .sidebar-brand {
        text-align: center;
        font-size: 18px;
        font-weight: 700;
        padding: 0.5rem 0 0.5rem 0;
        margin-top: -50px;
        margin-bottom: 0px;
        letter-spacing: 0.3px;
        border-bottom: 1px solid rgba(250,250,250,0.08);
    }

    /* Pin API status to bottom of sidebar */
    .api-status-box {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 280px;
        padding: 8px 16px 10px 16px;
        background: rgba(14,17,23,0.95);
        border-top: 1px solid rgba(250,250,250,0.08);
        z-index: 100;
    }
    .api-status-box p {
        font-size: 11px !important;
        margin: 0 !important;
        opacity: 0.55;
        color: #FAFAFA;
    }

    /* ── Top header bar ──────────────────────── */
    [data-testid="stHeader"] {
        height: 1.2rem;
        background: linear-gradient(90deg, rgba(14,17,23,0.95) 0%, rgba(14,17,23,0.6) 50%, transparent 100%) !important;
    }
    [data-testid="stHeader"] [data-testid="stToolbar"] {
        height: 1.2rem;
        top: 0;
    }

    /* ── Main content ────────────────────────── */
    .block-container {
        padding-top: 3.5rem;
        padding-bottom: 3rem;
    }

    /* ── Card styling ────────────────────────── */
    /* Target st.container(border=True) */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.08);
        background-color: rgba(255,255,255,0.02);
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        margin-bottom: 0.25rem !important;
        padding: 1rem;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border: 1px solid rgba(255,107,53,0.3);
        box-shadow: 0 4px 24px rgba(255,107,53,0.08);
        transition: all 0.2s ease;
    }

    /* Larger touch targets */
    .stButton > button {
        min-height: 40px;
        font-size: 15px;
    }

    /* Prevent zoom on iOS */
    input, select, textarea {
        font-size: 16px !important;
    }

    /* Nicer expanders */
    .streamlit-expanderHeader {
        font-size: 16px;
        font-weight: 600;
    }

    /* ── Modern segmented nav ────────────────── */
    .nav-container {
        display: flex;
        gap: 6px;
        background: rgba(255,255,255,0.04);
        border-radius: 14px;
        padding: 5px;
        margin-bottom: 1.5rem;
        border: 1px solid rgba(255,255,255,0.06);
    }
    .nav-btn {
        flex: 1;
        text-align: center;
        padding: 10px 16px;
        border-radius: 10px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        border: none;
        background: transparent;
        color: rgba(250,250,250,0.55);
        text-decoration: none;
        letter-spacing: 0.2px;
    }
    .nav-btn:hover {
        background: rgba(255,255,255,0.06);
        color: rgba(250,250,250,0.85);
    }
    .nav-btn.active {
        background: linear-gradient(135deg, #FF6B35 0%, #FF8F5E 100%);
        color: #fff;
        box-shadow: 0 2px 12px rgba(255,107,53,0.3);
    }
    .nav-icon {
        margin-right: 6px;
        font-size: 15px;
    }

    /* Hide streamlit default tabs if any */
    .stTabs [data-baseweb="tab-list"] { display: none; }
    .stTabs [data-baseweb="tab-border"] { display: none; }
    .stTabs [data-baseweb="tab-highlight"] { display: none; }

    /* ── Polished Event Card Content ──────────────── */
    .event-custom-header {
        margin-bottom: 1rem;
    }
    .event-name {
        font-size: 1.35rem;
        font-weight: 700;
        color: #FFFFFF;
        margin: 0 0 0.5rem 0;
        letter-spacing: -0.01em;
        line-height: 1.3;
    }
    .event-badge {
        display: inline-block;
        background: rgba(255, 107, 53, 0.12);
        color: #FF8F5E;
        font-size: 0.7rem;
        font-weight: 700;
        padding: 4px 8px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.5rem;
        border: 1px solid rgba(255, 107, 53, 0.15);
    }
    
    /* Grid layout for event details */
    .event-meta-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 12px 24px;
        margin-bottom: 0.5rem;
        background: rgba(255,255,255,0.02);
        padding: 12px;
        border-radius: 8px;
        border: 1px solid rgba(255,255,255,0.04);
    }
    
    .meta-item {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }
    
    .meta-label {
        font-size: 0.75rem;
        text-transform: uppercase;
        font-weight: 600;
        letter-spacing: 0.03em;
        color: rgba(255,255,255,0.4);
    }
    
    .meta-value {
        font-size: 0.95rem;
        color: rgba(255,255,255,0.9);
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    
    .meta-icon {
        opacity: 0.5;
        font-size: 1em;
    }

    /* Code styling adjustment */
    .meta-value code {
        background: rgba(0,0,0,0.3);
        border: 1px solid rgba(255,255,255,0.1);
        color: #FF8F5E;
        font-family: 'SF Mono', 'Roboto Mono', monospace;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.85em;
    }
</style>
""", unsafe_allow_html=True)


def render_sidebar_stats(series):
    """Show season stats in the sidebar."""
    total_events = len(series.events)
    total_sessions = sum(len(e.sessions) for e in series.events)

    race_count = 0
    practice_count = 0
    quali_count = 0
    other_count = 0
    for e in series.events:
        for s in e.sessions:
            if s.type == SessionType.RACE:
                race_count += 1
            elif s.type == SessionType.PRACTICE:
                practice_count += 1
            elif s.type == SessionType.QUALIFYING:
                quali_count += 1
            else:
                other_count += 1

    street_circuits = set()
    ovals = set()
    road_courses = set()
    for e in series.events:
        circuit = (e.venue.circuit or "").lower()
        if "street" in circuit:
            street_circuits.add(e.venue.circuit)
        elif any(kw in circuit for kw in ["speedway", "raceway", "mile", "oval"]):
            ovals.add(e.venue.circuit)
        elif e.venue.circuit:
            road_courses.add(e.venue.circuit)

    if series.events:
        first = series.events[0].start_date.strftime("%b %d").replace(" 0", " ")
        last = series.events[-1].end_date.strftime("%b %d").replace(" 0", " ")
        span = f"{first} → {last}"
    else:
        span = "—"

    unique_tracks = set(
        e.venue.circuit for e in series.events if e.venue.circuit
    )

    st.markdown("---")
    st.markdown("#### 📊 Season Overview")

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Events", total_events)
        st.metric("Races", race_count)
    with col_b:
        st.metric("Sessions", total_sessions)
        st.metric("Tracks", len(unique_tracks))

    st.caption(f"📅 {span}")

    st.markdown("---")
    st.markdown("#### 🏟️ Track Types")
    if street_circuits:
        st.markdown(f"🏙️ Streets: **{len(street_circuits)}**")
    if ovals:
        st.markdown(f"🔵 Ovals: **{len(ovals)}**")
    if road_courses:
        st.markdown(f"🟢 Road: **{len(road_courses)}**")

    st.markdown("---")
    st.markdown("#### 📋 Sessions Breakdown")
    st.caption(
        f"🏎️ Races: {race_count} · "
        f"🔧 Practice: {practice_count}\n\n"
        f"⏱️ Qualifying: {quali_count} · "
        f"📌 Other: {other_count}"
    )


def render_api_status():
    """Small read-only panel pinned to the very bottom of the sidebar."""
    serpapi = bool(os.environ.get("SERPAPI_KEY", ""))
    bing = bool(os.environ.get("BING_SEARCH_KEY", ""))
    google = bool(os.environ.get("GOOGLE_CSE_KEY", ""))

    if serpapi or bing or google:
        items = []
        if serpapi:
            items.append("🟢 SerpAPI")
        if bing:
            items.append("🟢 Bing")
        if google:
            items.append("🟢 Google CSE")
        status_text = " · ".join(items)
    else:
        status_text = "⚪ No search keys · add to .env"

    st.markdown(
        f'<div class="api-status-box"><p>{status_text}</p></div>',
        unsafe_allow_html=True,
    )


def render_upload_tab():
    """Upload Data section — supports JSON, PDF, DOCX, and TXT files."""
    st.markdown("### 📤 Upload Schedule Data")
    
    st.markdown("""
    Upload schedule data in various formats:
    - **JSON**: Previously exported schedule data
    - **PDF/Word/Text**: Documents containing schedule information (uses AI extraction)
    """)
    
    # File size limit (5MB)
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes
    
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["json", "pdf", "docx", "doc", "txt"],
        key="multi_format_uploader",
        help="Upload JSON, PDF, Word, or text file (max 5MB)",
    )
    
    if uploaded_file is not None:
        # Check file size
        file_size = len(uploaded_file.getvalue())
        if file_size > MAX_FILE_SIZE:
            st.error(f"File too large ({file_size / 1024 / 1024:.1f}MB). Maximum size is 5MB.")
            return
        
        file_ext = uploaded_file.name.lower().split('.')[-1]
        
        # JSON files use existing handler
        if file_ext == 'json':
            home.handle_upload(uploaded_file)
        else:
            # Document files use AI extraction
            handle_document_upload(uploaded_file)


def handle_document_upload(uploaded_file):
    """Handle PDF, DOCX, and TXT uploads with AI extraction."""
    try:
        from parsers import DocumentParser
        from ai import ScheduleExtractor
        
        with st.spinner("📄 Extracting text from document..."):
            # Parse document
            file_bytes = uploaded_file.getvalue()
            parser = DocumentParser.get_parser(uploaded_file.name)
            document_text = parser.extract_text(file_bytes, uploaded_file.name)
        
        st.success(f"✅ Extracted {len(document_text)} characters from document")
        
        # Show text preview in expander
        with st.expander("📝 View extracted text"):
            st.text_area(
                "Document content",
                document_text[:2000] + ("..." if len(document_text) > 2000 else ""),
                height=200,
                disabled=True,
            )
        
        # Extract schedule data using AI
        with st.spinner("🤖 Analyzing document with AI (this may take a moment)..."):
            extractor = ScheduleExtractor()
            result = extractor.extract_schedule(document_text, uploaded_file.name)
            validated = extractor.validate_extracted_data(result)
        
        series = validated["series"]
        validation_result = validated["validation"]
        
        # Show preview of extracted data
        st.markdown("### 🎯 Extracted Schedule Data")
        st.markdown(
            f"**Series:** {series.name} · **Season:** {series.season} · "
            f"**Events:** {len(series.events)}"
        )
        
        # Show validation summary
        if validation_result.is_valid:
            st.success("✅ Data validation passed")
        else:
            st.warning(f"⚠️ {len(validation_result.errors)} validation warnings")
        
        # Show events preview
        with st.expander(f"Preview {len(series.events)} events"):
            for event in series.events[:5]:
                st.markdown(
                    f"**{event.name}** — {event.start_date.strftime('%b %d, %Y')} · "
                    f"{event.venue.country}"
                )
            if len(series.events) > 5:
                st.caption(f"... and {len(series.events) - 5} more events")
        
        # Confirmation button
        if st.button("✅ Confirm & Load Data", type="primary", use_container_width=True):
            st.session_state.series = series
            st.session_state.original_series = series.model_copy(deep=True)
            st.session_state.validation_result = validation_result
            st.success("🎉 Schedule data loaded successfully!")
            st.rerun()
    
    except ImportError as e:
        st.error(f"❌ Missing dependency: {str(e)}")
        st.info("Run: `pip install -r requirements.txt` to install required packages")
    except ValueError as e:
        st.error(f"❌ Extraction failed: {str(e)}")
        if "GEMINI_API_KEY" in str(e):
            st.info("💡 Add GEMINI_API_KEY to your .env file to use AI extraction")
    except Exception as e:
        st.error(f"❌ Unexpected error: {str(e)}")
        import traceback
        with st.expander("🐛 View error details"):
            st.code(traceback.format_exc())


# Navigation items
NAV_ITEMS = [
    {"key": "scraper",     "icon": "🕷️", "label": "Scraper"},
    {"key": "view",        "icon": "👀", "label": "View Data"},
    {"key": "connectors",  "icon": "⚡", "label": "Test Connectors"},
    {"key": "search",      "icon": "🌐", "label": "Search Discovery"},
    {"key": "upload",      "icon": "📂", "label": "Upload Data"},
]


def main():
    """Main application entrypoint."""

    # Authentication Check
    if not auth.check_auth():
        st.stop()

    # ── Sidebar ──────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<p class="sidebar-brand">🏁 MotorsportBot</p>',
            unsafe_allow_html=True,
        )

        # Logout button (only if login is required)
        if auth.is_login_required():
            if st.button("Log Out", use_container_width=True):
                auth.logout()

        # Stats when data is loaded
        if "series" in st.session_state and st.session_state.series:
            render_sidebar_stats(st.session_state.series)

        # API status pinned to bottom
        render_api_status()

    # ── Navigation ───────────────────────────────────────────
    if "active_nav" not in st.session_state:
        st.session_state.active_nav = "connectors"

    active = st.session_state.active_nav

    # Render custom segmented control
    cols = st.columns(len(NAV_ITEMS))
    for i, item in enumerate(NAV_ITEMS):
        with cols[i]:
            btn_type = "primary" if active == item["key"] else "secondary"
            if st.button(
                f"{item['icon']}  {item['label']}",
                key=f"nav_{item['key']}",
                type=btn_type,
                use_container_width=True,
            ):
                st.session_state.active_nav = item["key"]
                st.rerun()

    st.markdown("")  # spacer

    # ── Content ──────────────────────────────────────────────
    if active == "scraper":
        scraper.render()
    elif active == "view":
        view.render()
    elif active == "connectors":
        home.render()
    elif active == "search":
        search_fallback.render()
    elif active == "upload":
        render_upload_tab()


if __name__ == "__main__":
    main()
