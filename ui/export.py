"""
Export helpers — download button for the main page.
"""

import streamlit as st
import json
import hashlib
from datetime import datetime


def render_download_button(series):
    """Render a compact download button."""
    export_data = generate_export_json(series)
    json_str = json.dumps(export_data, indent=2)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{series.series_id}_{series.season}_{timestamp}.json"

    st.download_button(
        label="📥 Download JSON",
        data=json_str,
        file_name=filename,
        mime="application/json",
        type="secondary",
    )


def generate_export_json(series):
    """Generate export JSON with manifest."""
    series_data = series.to_dict()

    series_json = json.dumps(series_data, sort_keys=True)
    sha256_hash = hashlib.sha256(series_json.encode()).hexdigest()

    provenance_summary = {}
    for event in series.events:
        for source in event.sources:
            provider = source.provider_name
            provenance_summary[provider] = provenance_summary.get(provider, 0) + 1

    validation_warnings = 0
    validation_errors = 0
    if "validation_result" in st.session_state:
        result = st.session_state.validation_result
        validation_warnings = len(result.warnings)
        validation_errors = len(result.errors)

    manifest = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "series_id": series.series_id,
        "season": series.season,
        "sha256": sha256_hash,
        "provenance_summary": provenance_summary,
        "validation_warnings": validation_warnings,
        "validation_errors": validation_errors,
    }

    return {
        "manifest": manifest,
        "series": series_data,
    }
