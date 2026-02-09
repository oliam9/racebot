"""
Export page - JSON preview and download.
"""

import streamlit as st
import json
import hashlib
from datetime import datetime


def render():
    """Render the export page."""
    # Check if data is loaded
    if "series" not in st.session_state or not st.session_state.series:
        st.warning("⚠️ No data loaded. Please go to **Home** to fetch or upload data.")
        return
    
    series = st.session_state.series
    
    st.title(f"📦 Export: {series.name} ({series.season})")
    
    # Validation check
    render_validation_status()
    
    # Export metadata
    render_export_metadata(series)
    
    # JSON preview
    render_json_preview(series)
    
    # Download button
    render_download_section(series)
    
    # Provenance summary
    render_provenance_summary(series)


def render_validation_status():
    """Show validation status before export."""
    if "validation_result" not in st.session_state:
        st.warning("⚠️ Data has not been validated. Run validation first.")
        return
    
    result = st.session_state.validation_result
    
    if result.is_valid:
        st.success(
            f"✅ **Data is valid** - "
            f"{len(result.warnings)} warnings (can be ignored)"
        )
    else:
        st.error(
            f"❌ **Data has errors** - "
            f"{len(result.errors)} errors must be fixed before export is recommended"
        )
        st.warning(
            "You can still export, but the data may not meet quality standards."
        )
        
        # Show error summary
        with st.expander("View Errors"):
            for error in result.errors:
                st.markdown(f"- {error.message}")


def render_export_metadata(series):
    """Display export metadata."""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Events", len(series.events))
    
    with col2:
        total_sessions = sum(len(e.sessions) for e in series.events)
        st.metric("Sessions", total_sessions)
    
    with col3:
        if "validation_result" in st.session_state:
            result = st.session_state.validation_result
            st.metric("Warnings", len(result.warnings))


def render_json_preview(series):
    """Show JSON preview."""
    st.subheader("📄 JSON Preview")
    
    # Generate JSON
    export_data = generate_export_json(series)
    json_str = json.dumps(export_data, indent=2)
    
    # Show preview (limited to first 1000 lines)
    lines = json_str.split('\n')
    preview_lines = lines[:1000]
    preview_str = '\n'.join(preview_lines)
    
    if len(lines) > 1000:
        preview_str += f"\n\n... ({len(lines) - 1000} more lines)"
    
    st.code(preview_str, language="json", line_numbers=False)
    
    # File size info
    size_bytes = len(json_str.encode('utf-8'))
    size_kb = size_bytes / 1024
    st.caption(f"File size: {size_kb:.1f} KB ({size_bytes:,} bytes)")


def render_download_section(series):
    """Render download button and options."""
    st.subheader("⬇️ Download")
    
    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{series.series_id}_{series.season}_{timestamp}.json"
    
    # Generate JSON
    export_data = generate_export_json(series)
    json_str = json.dumps(export_data, indent=2)
    
    # Download button
    st.download_button(
        label="📥 Download JSON",
        data=json_str,
        file_name=filename,
        mime="application/json",
        use_container_width=True,
        type="primary"
    )
    
    st.caption(f"Filename: `{filename}`")
    
    # Copy to clipboard option
    if st.button("📋 Copy to Clipboard", use_container_width=True):
        st.code(json_str, language="json")
        st.info("👆 Click the copy button in the top-right of the code block above")


def render_provenance_summary(series):
    """Display data provenance summary."""
    st.subheader("📚 Provenance Summary")
    
    # Collect all sources
    sources_by_provider = {}
    for event in series.events:
        for source in event.sources:
            provider = source.provider_name
            if provider not in sources_by_provider:
                sources_by_provider[provider] = {
                    "count": 0,
                    "urls": set(),
                    "latest_retrieval": None
                }
            
            sources_by_provider[provider]["count"] += 1
            sources_by_provider[provider]["urls"].add(source.url)
            
            if sources_by_provider[provider]["latest_retrieval"] is None or \
               source.retrieved_at > sources_by_provider[provider]["latest_retrieval"]:
                sources_by_provider[provider]["latest_retrieval"] = source.retrieved_at
    
    # Display summary
    for provider, info in sources_by_provider.items():
        with st.expander(f"**{provider}** - {info['count']} events"):
            st.markdown(f"- **Events sourced:** {info['count']}")
            st.markdown(f"- **Last retrieved:** {info['latest_retrieval']}")
            st.markdown(f"- **Source URLs:**")
            for url in info['urls']:
                st.markdown(f"  - `{url}`")


def generate_export_json(series):
    """
    Generate export JSON with manifest.
    
    Returns:
        Dictionary ready for JSON serialization
    """
    # Serialize series
    series_data = series.to_dict()
    
    # Generate hash
    series_json = json.dumps(series_data, sort_keys=True)
    sha256_hash = hashlib.sha256(series_json.encode()).hexdigest()
    
    # Build provenance summary
    provenance_summary = {}
    for event in series.events:
        for source in event.sources:
            provider = source.provider_name
            provenance_summary[provider] = provenance_summary.get(provider, 0) + 1
    
    # Get validation stats
    validation_warnings = 0
    validation_errors = 0
    if "validation_result" in st.session_state:
        result = st.session_state.validation_result
        validation_warnings = len(result.warnings)
        validation_errors = len(result.errors)
    
    # Build manifest
    manifest = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "series_id": series.series_id,
        "season": series.season,
        "sha256": sha256_hash,
        "provenance_summary": provenance_summary,
        "validation_warnings": validation_warnings,
        "validation_errors": validation_errors,
    }
    
    # Combine manifest and data
    return {
        "manifest": manifest,
        "series": series_data
    }
