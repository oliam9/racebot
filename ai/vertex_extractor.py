"""
Dynamic AI-powered schedule extractor using Google Gemini.

Two-phase extraction:
  Phase 1: Calendar page → event names, dates, URLs
  Phase 2: Individual event pages → session details
"""

import json
import os
import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


def _clean_html(html: str, max_chars: int = 300_000) -> str:
    """Strip non-content elements from HTML and truncate to max_chars."""
    html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<!--[\s\S]*?-->", "", html)
    html = re.sub(r"\s{2,}", " ", html)

    if len(html) > max_chars:
        logger.warning("HTML truncated from %d to %d chars", len(html), max_chars)
        html = html[:max_chars] + "\n... (truncated)"
    return html


def _parse_json_response(text: str) -> Any:
    """Parse JSON from an AI response, handling markdown fences and fixups."""
    text = text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        if text.startswith("json"):
            text = text[4:]

    # Find outermost JSON structure (object or array)
    first_brace = text.find("{")
    first_bracket = text.find("[")
    
    if first_bracket != -1 and (first_brace == -1 or first_bracket < first_brace):
        last = text.rfind("]")
        if last != -1:
            text = text[first_bracket : last + 1]
    elif first_brace != -1:
        last = text.rfind("}")
        if last != -1:
            text = text[first_brace : last + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        fixed = re.sub(r",(\s*[}\]])", r"\1", text)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as exc:
            raise ValueError(f"AI returned invalid JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# Phase 1 prompt: Extract calendar (event list + links)
# ---------------------------------------------------------------------------

_CALENDAR_PROMPT = """You are an expert at extracting motorsport schedule data from web pages.

From the following HTML, extract ALL race events/rounds for **{series_name} {season}**.

For each event, I need:
- name: Event/Grand Prix name
- start_date: Start date (YYYY-MM-DD)
- end_date: End date (YYYY-MM-DD)
- url: The FULL URL link to the individual event detail page (look for <a href="..."> links around the event). Use absolute URLs.
- venue: circuit name, city, country

The page URL is: {page_url}
Use this to resolve relative URLs to absolute ones.

Return ONLY valid JSON array:

[
  {{
    "name": "Qatar Grand Prix",
    "start_date": "2026-03-06",
    "end_date": "2026-03-08",
    "url": "https://example.com/event/qatar-gp",
    "venue": {{
      "circuit": "Lusail International Circuit",
      "city": "Lusail",
      "country": "Qatar",
      "timezone": "Asia/Qatar"
    }}
  }}
]

**Instructions:**
- Extract ALL events, even if they have no dates yet (use null for missing dates)
- url is CRITICAL — look for links (<a href>) in or around each event entry
- If no individual event URL is found, set url to null
- Make sure URLs are absolute (start with http)
- timezone: infer from the venue country/city if not stated

HTML Content:
{html}"""


# ---------------------------------------------------------------------------
# Phase 2 prompt: Extract sessions from an event detail page
# ---------------------------------------------------------------------------

_SESSIONS_PROMPT = """You are an expert at extracting motorsport session schedules from web pages.

From the following HTML, extract ALL sessions for the **{event_name}** ({series_name} {season}).

Sessions can be: Free Practice, Qualifying, Sprint, Race, Warm Up, etc.

Return ONLY valid JSON array:

[
  {{
    "name": "Free Practice 1",
    "type": "PRACTICE",
    "start": "YYYY-MM-DDTHH:MM:SS+HH:MM",
    "end": "YYYY-MM-DDTHH:MM:SS+HH:MM",
    "status": "SCHEDULED"
  }}
]

**Instructions:**
- Session types: PRACTICE, QUALIFYING, RACE, SPRINT, WARMUP, TEST, OTHER
- Status: SCHEDULED, TBD, UPDATED, CANCELLED
- Use ISO 8601 datetimes WITH timezone offset
- If times are not available, use null for start/end
- Include ALL sessions you can find (practice, qualy, race, sprint, warmup)
- Look for schedule tables, timetables, session listings
- If absolutely no session data is visible, return an empty array []

HTML Content:
{html}"""


# ---------------------------------------------------------------------------
# Full-page single-shot prompt (fallback for pages with everything)
# ---------------------------------------------------------------------------

_FULL_EXTRACTION_PROMPT = """You are an expert at extracting motorsport schedule data from web pages.

Extract ALL race events from the following HTML for **{series_name} {season}**.

Return ONLY valid JSON:

{{
  "series_id": "series_slug",
  "name": "{series_name}",
  "season": {season},
  "category": "OPENWHEEL",
  "events": [
    {{
      "event_id": "unique_id",
      "series_id": "series_slug",
      "name": "Event Name",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "venue": {{
        "circuit": "Circuit Name",
        "city": "City",
        "country": "Country",
        "timezone": "America/New_York"
      }},
      "sessions": [
        {{
          "session_id": "s1",
          "name": "Practice 1",
          "type": "PRACTICE",
          "start": "YYYY-MM-DDTHH:MM:SS+HH:MM",
          "status": "SCHEDULED"
        }}
      ]
    }}
  ]
}}

**Instructions:**
- Extract ALL events and their sessions
- Session types: PRACTICE, QUALIFYING, RACE, SPRINT, WARMUP, TEST, OTHER
- Session status: SCHEDULED, TBD, UPDATED, CANCELLED
- Use ISO 8601 dates and datetimes
- If sessions are not visible for an event, use empty array []
- Category: OPENWHEEL, ENDURANCE, RALLY, MOTORCYCLE, GT, TOURING, FORMULA, SPORTCAR, OTHER

HTML Content:
{html}"""


class DynamicExtractor:
    """Extract structured schedule data from raw HTML using Gemini AI."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = (
            model_name
            or os.getenv("AI_SCRAPER_MODEL", "gemini-2.5-flash")
        )

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. Add it to your .env file."
            )

        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(self.model_name)
            logger.info("DynamicExtractor initialised with model %s", self.model_name)
        except ImportError as exc:
            raise ImportError(
                "google-generativeai not installed. "
                "Run: pip install google-generativeai"
            ) from exc

    def _call_ai(self, prompt: str) -> str:
        """Call Gemini and return raw text response."""
        response = self._model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.1,
                "top_p": 0.95,
                "max_output_tokens": 8192,
            },
        )
        return response.text

    # ------------------------------------------------------------------
    # Phase 1: Calendar extraction
    # ------------------------------------------------------------------

    def extract_calendar(
        self, html: str, series_name: str, season: int, page_url: str,
        site_context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Phase 1: Extract event list + links from a calendar page.
        Returns list of dicts with: name, start_date, end_date, url, venue.
        """
        cleaned = _clean_html(html)
        prompt = _CALENDAR_PROMPT.format(
            series_name=series_name,
            season=season,
            page_url=page_url,
            html=cleaned,
        )
        
        if site_context:
            prompt += f"\n\n**IMPORTANT Site-Specific Hints:**\n{site_context}"

        raw = self._call_ai(prompt)
        events = _parse_json_response(raw)

        if isinstance(events, dict):
            events = events.get("events", [events])

        logger.info("Phase 1: found %d events from calendar", len(events))
        return events

    # ------------------------------------------------------------------
    # Phase 2: Session extraction from event detail page
    # ------------------------------------------------------------------

    def extract_sessions(
        self, html: str, event_name: str, series_name: str, season: int,
        site_context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Phase 2: Extract session details from an event detail page.
        Returns list of dicts with: name, type, start, end, status.
        """
        cleaned = _clean_html(html)
        prompt = _SESSIONS_PROMPT.format(
            event_name=event_name,
            series_name=series_name,
            season=season,
            html=cleaned,
        )

        if site_context:
            prompt += f"\n\n**IMPORTANT Site-Specific Hints:**\n{site_context}"

        raw = self._call_ai(prompt)
        sessions = _parse_json_response(raw)

        if isinstance(sessions, dict):
            sessions = sessions.get("sessions", [sessions])

        logger.info("Phase 2: found %d sessions for %s", len(sessions), event_name)
        return sessions

    # ------------------------------------------------------------------
    # Full extraction (single page fallback)
    # ------------------------------------------------------------------

    def extract(
        self, html: str, series_name: str, season: int,
        site_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Single-page extraction (calendar + sessions in one pass)."""
        cleaned = _clean_html(html)
        prompt = _FULL_EXTRACTION_PROMPT.format(
            series_name=series_name,
            season=season,
            html=cleaned,
        )

        if site_context:
            prompt += f"\n\n**IMPORTANT Site-Specific Hints:**\n{site_context}"

        raw = self._call_ai(prompt)
        data = _parse_json_response(raw)

        series_id = data.get("series_id", "unknown")
        for evt in data.get("events", []):
            evt.setdefault("series_id", series_id)

        return data
