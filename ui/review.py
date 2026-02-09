"""
Review & Edit page - main data editing interface.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from models.schema import Session
from models.enums import SessionType, SessionStatus
from validators import DataValidator
from normalizer import DataNormalizer


def render():
    """Render the review & edit page."""
    # Check if data is loaded
    if "series" not in st.session_state or not st.session_state.series:
        st.warning("⚠️ No data loaded. Please go to **Home** to fetch or upload data.")
        return
    
    series = st.session_state.series
    
    st.title(f"📝 Review & Edit: {series.name} ({series.season})")
    
    # Top action bar
    render_action_bar()
    
    # Two columns: event list | session editor
    col_left, col_right = st.columns([1, 2], gap="medium")
    
    with col_left:
        render_event_list(series)
    
    with col_right:
        render_session_editor(series)


def render_action_bar():
    """Render top action bar with global actions."""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🔄 Re-run Validation", use_container_width=True):
            run_validation()
    
    with col2:
        if st.button("✨ Apply Normalization", use_container_width=True):
            apply_normalization()
    
    with col3:
        if st.button("↩️ Revert Changes", use_container_width=True):
            revert_changes()
    
    with col4:
        if st.button("🗑️ Clear All Data", use_container_width=True):
            clear_data()
    
    # Show validation status
    if "validation_result" in st.session_state:
        result = st.session_state.validation_result
        if result.is_valid:
            st.success(f"✅ Valid - {len(result.warnings)} warnings")
        else:
            st.error(f"❌ {len(result.errors)} errors, {len(result.warnings)} warnings")


def render_event_list(series):
    """Render event list in sidebar."""
    st.subheader("📅 Events")
    
    # Search/filter
    search = st.text_input("🔍 Search events", key="event_search")
    
    # Filter events
    events = series.events
    if search:
        events = [
            e for e in events
            if search.lower() in e.name.lower()
        ]
    
    # Event selection
    if not events:
        st.info("No events found")
        return
    
    # Display as list
    for idx, event in enumerate(events):
        # Find validation issues for this event
        issue_count = 0
        if "validation_result" in st.session_state:
            validation = st.session_state.validation_result
            event_issues = [
                issue for issue in validation.errors + validation.warnings
                if issue.event_id == event.event_id
            ]
            issue_count = len(event_issues)
        
        # Create button for each event
        issue_badge = f" ⚠️ {issue_count}" if issue_count > 0 else ""
        button_label = f"{event.name}{issue_badge}"
        
        if st.button(
            button_label,
            key=f"event_select_{idx}",
            use_container_width=True
        ):
            st.session_state.selected_event_id = event.event_id
    
    st.divider()
    st.caption(f"Total: {len(events)} events")


def render_session_editor(series):
    """Render session editor for selected event."""
    # Check if event is selected
    if "selected_event_id" not in st.session_state:
        st.info("👈 Select an event from the list to edit")
        return
    
    # Find selected event
    event_id = st.session_state.selected_event_id
    event = next((e for e in series.events if e.event_id == event_id), None)
    
    if not event:
        st.error("Event not found")
        return
    
    st.subheader(f"🏁 {event.name}")
    
    # Event metadata
    with st.expander("📍 Event Details", expanded=False):
        render_event_details(event)
    
    # Sessions table
    st.markdown("### 📋 Sessions")
    
    if not event.sessions:
        st.info("No sessions for this event")
    else:
        render_sessions_table(event)
    
    # Add session button
    if st.button("➕ Add Session", use_container_width=True):
        add_session_modal(event)
    
    # Show validation issues for this event
    render_validation_issues(event_id)


def render_event_details(event):
    """Render editable event details."""
    # Event name
    event.name = st.text_input(
        "Event Name",
        value=event.name,
        key=f"event_name_{event.event_id}"
    )
    
    # Dates
    col1, col2 = st.columns(2)
    with col1:
        event.start_date = st.date_input(
            "Start Date",
            value=event.start_date,
            key=f"event_start_{event.event_id}"
        )
    with col2:
        event.end_date = st.date_input(
            "End Date",
            value=event.end_date,
            key=f"event_end_{event.event_id}"
        )
    
    # Venue
    st.markdown("**Venue**")
    event.venue.circuit = st.text_input(
        "Circuit",
        value=event.venue.circuit or "",
        key=f"venue_circuit_{event.event_id}"
    )
    
    col1, col2, col3 = st.columns(3)
    with col1:
        event.venue.city = st.text_input(
            "City",
            value=event.venue.city or "",
            key=f"venue_city_{event.event_id}"
        )
    with col2:
        event.venue.region = st.text_input(
            "Region/State",
            value=event.venue.region or "",
            key=f"venue_region_{event.event_id}"
        )
    with col3:
        event.venue.country = st.text_input(
            "Country",
            value=event.venue.country,
            key=f"venue_country_{event.event_id}"
        )
    
    # Timezone
    event.venue.timezone = st.text_input(
        "Timezone (IANA)",
        value=event.venue.timezone,
        key=f"venue_tz_{event.event_id}",
        help="e.g., America/New_York, Europe/London"
    )
    
    if event.venue.inferred_timezone:
        st.caption("⚠️ Timezone was inferred from location")


def render_sessions_table(event):
    """Render sessions as an editable table."""
    # Convert sessions to DataFrame for display
    sessions_data = []
    for idx, session in enumerate(event.sessions):
        sessions_data.append({
            "idx": idx,
            "Type": session.type.value,
            "Name": session.name,
            "Start": session.start or "TBD",
            "End": session.end or "TBD",
            "Status": session.status.value,
        })
    
    df = pd.DataFrame(sessions_data)
    
    # Display with st.dataframe (read-only preview)
    st.dataframe(
        df[["Type", "Name", "Start", "End", "Status"]],
        use_container_width=True,
        hide_index=True
    )
    
    # Edit session modal
    st.markdown("**Edit Session:**")
    session_options = [f"{i}: {s.name}" for i, s in enumerate(event.sessions)]
    selected = st.selectbox(
        "Select session to edit",
        options=range(len(event.sessions)),
        format_func=lambda i: session_options[i],
        key=f"session_selector_{event.event_id}"
    )
    
    if selected is not None:
        render_session_edit_form(event, selected)


def render_session_edit_form(event, session_idx):
    """Render edit form for a single session."""
    session = event.sessions[session_idx]
    
    with st.form(key=f"session_edit_{event.event_id}_{session_idx}"):
        st.markdown(f"**Editing: {session.name}**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            session_type = st.selectbox(
                "Type",
                options=[t.value for t in SessionType],
                index=[t.value for t in SessionType].index(session.type.value),
                key=f"type_{session_idx}"
            )
        
        with col2:
            session_status = st.selectbox(
                "Status",
                options=[s.value for s in SessionStatus],
                index=[s.value for s in SessionStatus].index(session.status.value),
                key=f"status_{session_idx}"
            )
        
        session_name = st.text_input(
            "Name",
            value=session.name,
            key=f"name_{session_idx}"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            start_time = st.text_input(
                "Start (ISO-8601)",
                value=session.start or "",
                key=f"start_{session_idx}",
                help="Format: 2024-05-26T12:45:00-04:00"
            )
        with col2:
            end_time = st.text_input(
                "End (ISO-8601)",
                value=session.end or "",
                key=f"end_{session_idx}",
                help="Format: 2024-05-26T16:30:00-04:00"
            )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("💾 Save Changes", use_container_width=True):
                # Update session
                session.type = SessionType(session_type)
                session.status = SessionStatus(session_status)
                session.name = session_name
                session.start = start_time if start_time else None
                session.end = end_time if end_time else None
                st.success("✅ Session updated")
                st.rerun()
        
        with col2:
            if st.form_submit_button("🗑️ Delete Session", use_container_width=True):
                event.sessions.pop(session_idx)
                st.success("✅ Session deleted")
                st.rerun()


def add_session_modal(event):
    """Show modal to add new session."""
    # This would ideally be a modal, but Streamlit doesn't have native modals
    # Use expander as fallback
    with st.expander("➕ Add New Session", expanded=True):
        with st.form(key=f"add_session_{event.event_id}"):
            session_name = st.text_input("Name", value="New Session")
            session_type = st.selectbox(
                "Type",
                options=[t.value for t in SessionType],
                index=0
            )
            start_time = st.text_input(
                "Start (ISO-8601)",
                value="",
                help="e.g., 2024-05-26T12:45:00-04:00"
            )
            
            if st.form_submit_button("Add"):
                # Create new session
                new_session = Session(
                    session_id=f"{event.event_id}_session_{len(event.sessions)}",
                    type=SessionType(session_type),
                    name=session_name,
                    start=start_time if start_time else None,
                    end=None,
                    status=SessionStatus.SCHEDULED if start_time else SessionStatus.TBD
                )
                event.sessions.append(new_session)
                st.success("✅ Session added")
                st.rerun()


def render_validation_issues(event_id):
    """Display validation issues for an event."""
    if "validation_result" not in st.session_state:
        return
    
    result = st.session_state.validation_result
    
    # Filter issues for this event
    errors = [e for e in result.errors if e.event_id == event_id]
    warnings = [w for w in result.warnings if w.event_id == event_id]
    
    if not errors and not warnings:
        return
    
    st.divider()
    st.subheader("⚠️ Validation Issues")
    
    if errors:
        st.error(f"**{len(errors)} Errors:**")
        for error in errors:
            st.markdown(f"- ❌ {error.message}")
            if error.suggested_fix:
                st.caption(f"  💡 Suggestion: {error.suggested_fix}")
    
    if warnings:
        st.warning(f"**{len(warnings)} Warnings:**")
        for warning in warnings:
            st.markdown(f"- ⚠️ {warning.message}")


# Action handlers
def run_validation():
    """Re-run validation on current data."""
    if "series" in st.session_state:
        validator = DataValidator()
        result = validator.validate_series(st.session_state.series)
        st.session_state.validation_result = result
        st.success("✅ Validation complete")
        st.rerun()


def apply_normalization():
    """Apply normalization suggestions."""
    if "series" in st.session_state:
        normalizer = DataNormalizer()
        for event in st.session_state.series.events:
            normalizer.normalize_event(event, apply_suggestions=True)
        st.success("✅ Normalization applied")
        run_validation()  # Re-validate after normalization
        st.rerun()


def revert_changes():
    """Revert to original fetched data."""
    if "original_series" in st.session_state:
        st.session_state.series = st.session_state.original_series.model_copy(deep=True)
        run_validation()
        st.success("✅ Changes reverted")
        st.rerun()


def clear_data():
    """Clear all session data."""
    keys_to_clear = ["series", "original_series", "validation_result", "selected_event_id"]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
    st.success("✅ Data cleared")
    st.rerun()
