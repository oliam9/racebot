"""
Search Discovery UI — Streamlit tab for discovering series data
via search APIs when no dedicated connector exists.

API keys are loaded exclusively from environment variables (.env file).
No secrets are ever entered or displayed in the UI.
"""

import os
import streamlit as st
from datetime import datetime
from typing import Optional

from search.client import get_search_client, SearchClient
from search.orchestrator import SearchFallback, SearchOutput
from search.domain_trust import DomainTrustModel, SERIES_DEFAULTS


# ------------------------------------------------------------------
# Known series presets (for the dropdown)
# ------------------------------------------------------------------

SERIES_PRESETS = {
    "IMSA WeatherTech": {"id": "imsa", "cat": "ENDURANCE"},
    "FIA WEC": {"id": "wec", "cat": "ENDURANCE"},
    "MotoGP": {"id": "motogp", "cat": "MOTORCYCLE"},
    "Formula 1": {"id": "f1", "cat": "OPENWHEEL"},
    "WRC": {"id": "wrc", "cat": "RALLY"},
    "NASCAR Cup Series": {"id": "nascar", "cat": "OTHER"},
    "V8 Supercars": {"id": "v8supercars", "cat": "TOURING"},
    "Super Formula": {"id": "super_formula", "cat": "OPENWHEEL"},
    "Super GT": {"id": "super_gt", "cat": "GT"},
    "Custom…": {"id": "", "cat": "OTHER"},
}


def _get_api_config():
    """Read search API config from environment only."""
    provider = os.environ.get("SEARCH_PROVIDER", "serpapi")
    key_env = {
        "serpapi": "SERPAPI_KEY",
        "bing": "BING_SEARCH_KEY",
        "google_cse": "GOOGLE_CSE_KEY",
    }.get(provider, "SERPAPI_KEY")
    api_key = os.environ.get(key_env, "")
    cse_cx = os.environ.get("GOOGLE_CSE_CX", "")
    return provider, api_key, cse_cx


def render():
    """Render the search discovery tab."""
    provider, api_key, cse_cx = _get_api_config()
    has_key = bool(api_key)

    st.caption(
        "Discover schedule data for any series via web search. "
        "API keys are loaded from the `.env` file."
    )

    # ----------------------------------------------------------
    # Series & season selection
    # ----------------------------------------------------------
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        series_choice = st.selectbox(
            "Series",
            list(SERIES_PRESETS.keys()),
            key="search_series",
        )

    with col2:
        season_year = st.number_input(
            "Season",
            min_value=2020,
            max_value=2030,
            value=datetime.now().year,
            key="search_season",
        )

    preset = SERIES_PRESETS[series_choice]

    # Custom series input
    custom_name = ""
    custom_id = ""
    if series_choice == "Custom…":
        c1, c2 = st.columns(2)
        with c1:
            custom_name = st.text_input("Series name", key="custom_series_name")
        with c2:
            custom_id = st.text_input("Series ID (slug)", key="custom_series_id")

    series_name = custom_name if series_choice == "Custom…" else series_choice
    series_id = custom_id if series_choice == "Custom…" else preset["id"]
    category = preset["cat"]

    with col3:
        st.markdown("")
        st.markdown("")
        run_btn = st.button(
            "🔎 Search",
            type="primary",
            key="run_search",
            disabled=not has_key,
        )

    if not has_key:
        st.warning(
            "🔑 No search API key found. Add your key to the `.env` file "
            "(see `.env.example` for the format) and restart the app."
        )

    # ----------------------------------------------------------
    # Execute search
    # ----------------------------------------------------------
    if run_btn:
        if not series_name or not series_id:
            st.error("Please provide a series name and ID.")
            return

        try:
            kwargs = {"api_key": api_key}
            if provider == "google_cse":
                kwargs["cx"] = cse_cx
            client = get_search_client(provider, **kwargs)
        except Exception as e:
            st.error(f"Failed to create search client: {e}")
            return

        status_text = st.empty()

        def on_status(msg: str):
            status_text.caption(f"⏳ {msg}")

        fallback = SearchFallback(
            search_client=client,
            series_name=series_name,
            series_id=series_id,
            season_year=int(season_year),
            category=category,
        )

        with st.spinner("Discovering schedule data…"):
            output = fallback.run(on_status=on_status)

        status_text.empty()
        st.session_state.search_output = output

        if output.extracted_draft and output.extracted_draft.events:
            st.session_state.series = output.extracted_draft

        st.rerun()

    # ----------------------------------------------------------
    # Display results
    # ----------------------------------------------------------
    output: Optional[SearchOutput] = st.session_state.get("search_output")
    if not output:
        return

    _render_output(output)


def _render_output(output: SearchOutput):
    """Render the search output with warnings, draft, and provenance."""

    # Stats bar
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        event_count = len(output.extracted_draft.events) if output.extracted_draft else 0
        st.metric("Events found", event_count)
    with col_b:
        st.metric("Pages fetched", output.total_pages_fetched)
    with col_c:
        st.metric("Queries run", len(output.provenance))
    with col_d:
        st.metric("Missing fields", len(output.missing_fields))

    # Warnings
    if output.warnings:
        with st.expander(f"⚠ Warnings ({len(output.warnings)})", expanded=False):
            for w in output.warnings:
                if w.startswith("⚠"):
                    st.warning(w)
                elif "[error]" in w.lower():
                    st.error(w)
                else:
                    st.caption(w)

    # Draft events
    if output.extracted_draft:
        st.markdown("---")
        st.markdown("#### 📋 Draft Schedule")
        st.caption(
            f"{output.extracted_draft.name} — {output.extracted_draft.season} season"
        )

        from ui.home import render_events
        render_events(output.extracted_draft)

    # Missing fields
    if output.missing_fields:
        with st.expander(
            f"❓ Missing Fields ({len(output.missing_fields)})", expanded=False
        ):
            for mf in output.missing_fields:
                st.markdown(
                    f"- **{mf.event_name}** → `{mf.field_name}`: {mf.reason}"
                )

    # Candidate pages
    if output.candidate_event_pages:
        with st.expander(
            f"🔗 Candidate Pages ({len(output.candidate_event_pages)})",
            expanded=False,
        ):
            for cp in output.candidate_event_pages:
                tier_badge = {
                    "tier1": "🟢",
                    "tier2": "🟡",
                    "unknown": "⚪",
                }.get(cp.tier, "⚪")

                st.markdown(
                    f"{tier_badge} **{cp.title[:60]}** · "
                    f"score={cp.score:.0f} · [{cp.url[:50]}…]({cp.url})"
                )

    # Provenance
    if output.provenance:
        with st.expander(
            f"📜 Provenance ({len(output.provenance)} queries)", expanded=False
        ):
            for p in output.provenance:
                st.caption(
                    f"🔍 `{p.query}` via {p.provider} "
                    f"→ {p.result_count} results"
                )
                if p.chosen_urls:
                    for u in p.chosen_urls[:2]:
                        st.caption(f"   ↳ {u}")
