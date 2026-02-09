"""
Home page - series/season selection and data fetching.
"""

import streamlit as st
import json
from datetime import datetime
from connectors import list_available_series, get_connector
from models.schema import Series
from validators import DataValidator
from normalizer import DataNormalizer


def render():
    """Render the home page."""
    st.title("🏁 Motorsport Data Collector")
    st.markdown("Fetch, edit, and export motorsport schedule data")
    
    # Two columns: Fetch new data | Upload existing data
    col1, col2 = st.columns(2)
    
    with col1:
        st.header("📥 Fetch New Data")
        render_fetch_section()
    
    with col2:
        st.header("📤 Upload Previous Export")
        render_upload_section()
    
    # Show current data status
    if "series" in st.session_state and st.session_state.series:
        st.divider()
        st.success(
            f"✅ Loaded: **{st.session_state.series.name}** "
            f"({st.session_state.series.season})"
        )
        st.info(f"📊 {len(st.session_state.series.events)} events loaded")


def render_fetch_section():
    """Render the fetch new data section."""
    # Get available series
    available_series = list_available_series()
    
    if not available_series:
        st.error("No data connectors available")
        return
    
    # Series selector
    series_options = {
        f"{s.name} ({s.connector_id})": s.series_id
        for s in available_series
    }
    
    selected_display = st.selectbox(
        "Select Series",
        options=list(series_options.keys()),
        key="series_selector"
    )
    
    selected_series_id = series_options[selected_display]
    
    # Season input
    current_year = datetime.now().year
    season = st.number_input(
        "Season (Year)",
        min_value=2020,
        max_value=current_year + 1,
        value=current_year,
        key="season_input"
    )
    
    # Fetch button
    if st.button("🚀 Fetch & Build Draft", type="primary", use_container_width=True):
        fetch_data(selected_series_id, season)


def render_upload_section():
    """Render the upload previous export section."""
    st.markdown("Upload a previously exported JSON file to continue editing")
    
    uploaded_file = st.file_uploader(
        "Choose JSON file",
        type=["json"],
        key="json_uploader"
    )
    
    if uploaded_file is not None:
        try:
            # Read and parse JSON
            content = uploaded_file.read().decode("utf-8")
            data = json.loads(content)
            
            # Check if it has export manifest
            if "manifest" in data and "series" in data:
                series_data = data["series"]
            else:
                # Assume it's just the series data
                series_data = data
            
            # Load into Series model
            series = Series.from_dict(series_data)
            
            # Store in session state
            st.session_state.series = series
            st.session_state.original_series = series.model_copy(deep=True)
            
            # Run validation
            validator = DataValidator()
            validation_result = validator.validate_series(series)
            st.session_state.validation_result = validation_result
            
            st.success(f"✅ Loaded {series.name} ({series.season})")
            st.info(f"📊 {len(series.events)} events loaded")
            
            # Show validation summary
            if validation_result.total_issues > 0:
                st.warning(
                    f"⚠️ {validation_result.total_issues} validation issues found "
                    f"({len(validation_result.errors)} errors, "
                    f"{len(validation_result.warnings)} warnings)"
                )
            
            # Suggest switching to review page
            st.info("👉 Go to **Review & Edit** page to view and edit the data")
            
        except Exception as e:
            st.error(f"Failed to load JSON: {str(e)}")


def fetch_data(series_id: str, season: int):
    """
    Fetch data for a series and season.
    
    Args:
        series_id: Series identifier
        season: Season year
    """
    with st.spinner("Fetching data..."):
        try:
            # Find connector
            connector = None
            for series_desc in list_available_series():
                if series_desc.series_id == series_id:
                    connector = get_connector(series_desc.connector_id)
                    break
            
            if not connector:
                st.error(f"No connector found for series: {series_id}")
                return
            
            # Fetch raw data
            st.info(f"📡 Fetching from {connector.name}...")
            raw_payload = connector.fetch_season(series_id, season)
            
            # Extract events
            st.info("🔍 Extracting events...")
            events = connector.extract(raw_payload)
            
            # Normalize
            st.info("🔧 Normalizing data...")
            events = connector.normalize(events)
            
            # Create Series object
            series_desc = next(
                s for s in connector.supported_series()
                if s.series_id == series_id
            )
            
            series = Series(
                series_id=series_id,
                name=series_desc.name,
                season=season,
                category=series_desc.category,
                events=events
            )
            
            # Validate
            st.info("✅ Validating...")
            validator = DataValidator()
            validation_result = validator.validate_series(series)
            
            # Store in session state
            st.session_state.series = series
            st.session_state.original_series = series.model_copy(deep=True)
            st.session_state.validation_result = validation_result
            
            st.success(
                f"✅ Successfully fetched {len(events)} events for "
                f"{series_desc.name} {season}"
            )
            
            # Show validation summary
            if validation_result.total_issues > 0:
                st.warning(
                    f"⚠️ {validation_result.total_issues} validation issues found "
                    f"({len(validation_result.errors)} errors, "
                    f"{len(validation_result.warnings)} warnings)"
                )
            else:
                st.success("✅ No validation issues found!")
            
            st.info("👉 Go to **Review & Edit** page to view and edit the data")
            
        except Exception as e:
            st.error(f"Failed to fetch data: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
