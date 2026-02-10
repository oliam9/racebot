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
        "🔍 Discover schedule data for any series. Use **web search** via APIs (Google/Bing) "
        "or provide a **direct URL** for AI-powered scraping."
    )

    # ----------------------------------------------------------
    # Mode selection: Search API or Direct URL
    # ----------------------------------------------------------
    mode = st.radio(
        "Discovery Method",
        ["🌐 Web Search (API)", "📄 Direct URL Scraping"],
        horizontal=True,
        help="Choose web search to find schedule pages automatically, or provide a direct URL to scrape.",
    )
    
    st.divider()
    
    # ----------------------------------------------------------
    # Series & season selection (common for both modes)
    # ----------------------------------------------------------
    col1, col2 = st.columns([3, 1])

    with col1:
        series_choice = st.selectbox(
            "Series",
            list(SERIES_PRESETS.keys()),
            key="search_series",
        )

    with col2:
        season_year = st.number_input(
            "Season",
            min_value=2026,
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
    
    # ----------------------------------------------------------
    # Mode-specific inputs
    # ----------------------------------------------------------
    if mode == "📄 Direct URL Scraping":
        _render_url_scraping_mode(series_name, series_id, season_year, category)
    else:
        _render_search_api_mode(series_name, series_id, season_year, category, has_key, api_key, provider, cse_cx)


def _render_url_scraping_mode(series_name: str, series_id: str, season_year: int, category: str):
    """Render the direct URL scraping interface."""
    
    # URL input
    target_url = st.text_input(
        "🌐 Schedule Page URL",
        placeholder="https://example.com/schedule",
        help="Paste the URL of the official schedule page. The AI will extract race data from this page.",
        key="direct_url_input",
    )
    
    # AI Model Selection
    st.markdown("**🤖 AI Model Selection**")
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        ai_model = st.selectbox(
            "Choose Model",
            [
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-2.0-flash-exp",
            ],
            index=0,
            help="Flash 2.5: Faster. Pro 2.5: More accurate. Exp 2.0: Experimental features.",
            label_visibility="collapsed"
        )
    
    with col2:
        if "flash" in ai_model.lower():
            st.info("⚡ Fast")
        elif "exp" in ai_model.lower():
            st.info("🧪 Experimental")
        else:
            st.info("🎯 Accurate")
    
    with col3:
        scrape_btn = st.button(
            "🤖 Extract",
            type="primary",
            use_container_width=True,
            disabled=not target_url,
        )
    
    # Check Gemini API key
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    
    if not gemini_key:
        st.warning(
            "⚠️ Google Gemini API key not found. Add `GEMINI_API_KEY` "
            "to your `.env` file and restart the app."
        )
        return
    
    # Safety info
    with st.expander("ℹ️ How URL Scraping Works", expanded=False):
        st.markdown("""
        **AI-Powered Extraction Process (using Google Gemini):**
        
        1. 🌐 **Fetch**: Uses Playwright to load the page (handles JavaScript)
        2. 🤖 **Extract**: Gemini AI reads the page content and identifies race events, dates, venues
        3. ✅ **Structure**: Converts unstructured data to our schema format
        4. 📊 **Review**: Review and edit the extracted data
        
        **Model Comparison:**
        
        | Model | Speed | Accuracy | Best For |
        |-------|-------|----------|----------|
        | **Gemini 2.5 Flash** | ⚡⚡⚡ Very Fast | ✅ Good | Simple HTML, quick extraction |
        | **Gemini 2.5 Pro** | ⚡⚡ Fast | ✅✅ Excellent | Complex pages, JavaScript-heavy |
        | **Gemini 2.0 Flash Exp** | ⚡⚡⚡ Very Fast | ✅✅ Excellent | Experimental, latest features |
        
        **Safety Features:**
        - Rate limiting (max 3 requests/minute per domain)
        - Respects robots.txt
        - User-agent identification
        - Request delays to avoid detection
        - Caches responses (24 hours) to avoid re-fetching
        
        **Best Practices:**
        - Use official championship websites
        - Provide specific schedule/calendar pages
        - Start with Flash, upgrade to Pro if needed
        - Avoid excessive re-scraping (uses cache automatically)
        """)
    
    if scrape_btn and target_url:
        _execute_url_scraping(
            url=target_url,
            series_name=series_name,
            series_id=series_id,
            season_year=season_year,
            category=category,
            ai_model=ai_model,
        )


def _render_search_api_mode(
    series_name: str, 
    series_id: str, 
    season_year: int, 
    category: str,
    has_key: bool,
    api_key: str,
    provider: str,
    cse_cx: str
):
    """Render the web search API interface."""
    
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
    if output:
        _render_output(output)


def _execute_url_scraping(
    url: str,
    series_name: str,
    series_id: str,
    season_year: int,
    category: str,
    ai_model: str = "gemini-2.5-flash",
):
    """Execute AI-powered URL scraping."""
    import time
    from search.ai_scraper import AIScraper, ScrapingResult
    
    status = st.empty()
    progress = st.progress(0)
    
    try:
        # Initialize scraper
        status.info(f"🤖 Initializing {ai_model}...")
        progress.progress(10)
        time.sleep(0.5)
        
        scraper = AIScraper(
            ai_provider="google gemini",
            ai_model=ai_model,
            requests_per_minute=3,
            cache_hours=24
        )
        
        # Fetch page
        status.info(f"🌐 Fetching {url}...")
        progress.progress(30)
        
        result: ScrapingResult = scraper.scrape_schedule_page(
            url=url,
            series_name=series_name,
            season_year=season_year,
        )
        
        progress.progress(60)
        
        # Parse with AI
        status.info(f"🤖 Extracting data with {ai_model}...")
        progress.progress(80)
        
        if result.success and result.series_data:
            status.success("✅ Extraction complete!")
            progress.progress(100)
            time.sleep(0.5)
            
            # Convert to Series object
            from models.schema import Series
            series = Series.model_validate(result.series_data)
            
            # Store in session
            st.session_state.series = series
            st.session_state.search_output = None  # Clear previous search output
            
            status.empty()
            progress.empty()
            
            # Display results like in connector search
            st.success(f"✅ Extracted {len(series.events)} events from {series.name}")
            
            # Show summary
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Events", len(series.events))
            with col2:
                total_sessions = sum(len(event.sessions) for event in series.events)
                st.metric("Sessions", total_sessions)
            with col3:
                st.metric("Season", series.season)
            
            # Display events table
            st.subheader("📅 Extracted Events")
            events_data = []
            for event in series.events:
                events_data.append({
                    "Event": event.name,
                    "Date": f"{event.start_date} to {event.end_date}",
                    "Venue": event.venue.circuit if event.venue else "N/A",
                    "Location": f"{event.venue.city or ''}, {event.venue.country}" if event.venue else "N/A",
                    "Sessions": len(event.sessions)
                })
            
            import pandas as pd
            df = pd.DataFrame(events_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            # Show extraction stats
            with st.expander("📊 Extraction Stats"):
                st.write(f"**Fetch Time:** {result.fetch_time_ms:.0f}ms")
                st.write(f"**Extraction Time:** {result.extraction_time_ms:.0f}ms")
                st.write(f"**Content Size:** {result.content_length:,} bytes")
                st.write(f"**Cached:** {'Yes' if result.cached else 'No'}")
                st.write(f"**Model Used:** {ai_model}")
            progress.empty()
            st.rerun()
        else:
            status.error(f"❌ Extraction failed: {result.error_message}")
            progress.empty()
            
            if result.warnings:
                with st.expander("⚠️ Warnings", expanded=True):
                    for warning in result.warnings:
                        st.warning(warning)
            
    except Exception as e:
        status.error(f"❌ Scraping failed: {str(e)}")
        progress.empty()
        import traceback
        st.code(traceback.format_exc())


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
