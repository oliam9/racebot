"""
Tests for the Dynamic AI Extractor and Connector.
"""

import json
import pytest
from datetime import datetime, date
from unittest.mock import patch, MagicMock

from ai.vertex_extractor import DynamicExtractor, _clean_html, _parse_json_response


# ===================================================================
# HTML Cleaning
# ===================================================================


class TestCleanHtml:
    def test_strips_script_tags(self):
        html = '<div>Hello</div><script>alert("x")</script><p>World</p>'
        assert "<script" not in _clean_html(html)
        assert "Hello" in _clean_html(html)
        assert "World" in _clean_html(html)

    def test_strips_style_tags(self):
        html = "<style>body{color:red}</style><div>Content</div>"
        assert "<style" not in _clean_html(html)
        assert "Content" in _clean_html(html)

    def test_truncates_long_html(self):
        html = "x" * 500_000
        result = _clean_html(html, max_chars=1000)
        assert len(result) < 1100  # 1000 + truncation message

    def test_collapses_whitespace(self):
        html = "<div>Hello     World</div>"
        assert "     " not in _clean_html(html)


# ===================================================================
# JSON Parsing
# ===================================================================


class TestParseJsonResponse:
    def test_plain_json(self):
        data = _parse_json_response('{"events": []}')
        assert data == {"events": []}

    def test_json_with_markdown_fences(self):
        text = '```json\n{"events": []}\n```'
        data = _parse_json_response(text)
        assert data == {"events": []}

    def test_json_with_surrounding_text(self):
        text = 'Here is the data:\n{"events": []}\nDone!'
        data = _parse_json_response(text)
        assert data == {"events": []}

    def test_fixes_trailing_commas(self):
        text = '{"events": [1, 2, 3,]}'
        data = _parse_json_response(text)
        assert data["events"] == [1, 2, 3]

    def test_raises_on_invalid(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_json_response("not json at all")


# ===================================================================
# DynamicExtractor
# ===================================================================


class TestDynamicExtractor:
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    @patch("google.generativeai.configure")
    @patch("google.generativeai.GenerativeModel")
    def test_extract_basic(self, mock_model_cls, mock_configure):
        # Mock Gemini response
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "series_id": "motogp",
            "name": "MotoGP",
            "season": 2026,
            "category": "MOTORCYCLE",
            "events": [
                {
                    "event_id": "motogp_2026_r1",
                    "series_id": "motogp",
                    "name": "Qatar Grand Prix",
                    "start_date": "2026-03-06",
                    "end_date": "2026-03-08",
                    "venue": {
                        "circuit": "Lusail International Circuit",
                        "city": "Lusail",
                        "country": "Qatar",
                        "timezone": "Asia/Qatar",
                    },
                    "sessions": [],
                }
            ],
        })
        mock_model_cls.return_value.generate_content.return_value = mock_response

        extractor = DynamicExtractor()
        result = extractor.extract("<html><body>MotoGP Calendar</body></html>", "MotoGP", 2026)

        assert result["series_id"] == "motogp"
        assert len(result["events"]) == 1
        assert result["events"][0]["name"] == "Qatar Grand Prix"


# ===================================================================
# DynamicAIConnector
# ===================================================================


class TestDynamicAIConnector:
    def test_connector_properties(self):
        from connectors.dynamic_connector import DynamicAIConnector

        conn = DynamicAIConnector()
        assert conn.id == "dynamic_ai"
        assert conn.needs_url is True
        assert "AI" in conn.name

    def test_supported_series_not_empty(self):
        from connectors.dynamic_connector import DynamicAIConnector

        conn = DynamicAIConnector()
        series = conn.supported_series()
        assert len(series) > 0
        # Should include well-known series
        ids = [s.series_id for s in series]
        assert "motogp" in ids
        assert "f1" in ids

    def test_set_target_url(self):
        from connectors.dynamic_connector import DynamicAIConnector

        conn = DynamicAIConnector()
        conn.set_target_url("https://example.com/calendar")
        assert conn._target_url == "https://example.com/calendar"

    def test_fetch_season_raises_without_url(self):
        from connectors.dynamic_connector import DynamicAIConnector

        conn = DynamicAIConnector()
        with pytest.raises(ValueError, match="No URL set"):
            conn.fetch_season("motogp", 2026)

    def test_extract_converts_json_to_events(self):
        from connectors.dynamic_connector import DynamicAIConnector
        from connectors.base import RawSeriesPayload

        conn = DynamicAIConnector()
        raw = RawSeriesPayload(
            content=json.dumps({
                "series_id": "f1",
                "events": [
                    {
                        "event_id": "f1_2026_r1",
                        "series_id": "f1",
                        "name": "Bahrain Grand Prix",
                        "start_date": "2026-03-06",
                        "end_date": "2026-03-08",
                        "venue": {
                            "circuit": "Bahrain International Circuit",
                            "city": "Sakhir",
                            "country": "Bahrain",
                            "timezone": "Asia/Bahrain",
                        },
                        "sessions": [
                            {
                                "session_id": "fp1",
                                "name": "Practice 1",
                                "type": "PRACTICE",
                                "status": "SCHEDULED",
                            }
                        ],
                    }
                ],
            }),
            content_type="application/json",
            url="https://example.com",
            retrieved_at=datetime.utcnow(),
            metadata={"series_id": "f1", "season": 2026},
        )

        events = conn.extract(raw)
        assert len(events) == 1
        assert events[0].name == "Bahrain Grand Prix"
        assert events[0].venue.country == "Bahrain"
        assert len(events[0].sessions) == 1
        assert events[0].sessions[0].name == "Practice 1"


# ===================================================================
# Registration
# ===================================================================


class TestConnectorRegistration:
    def test_dynamic_ai_not_in_registry(self):
        """Dynamic AI connector lives in its own tab, not in connector registry."""
        from connectors import get_connector

        conn = get_connector("dynamic_ai")
        assert conn is None  # Not registered — used directly by AI Scrapper tab

    def test_dynamic_ai_standalone(self):
        """Dynamic AI connector works when instantiated directly."""
        from connectors.dynamic_connector import DynamicAIConnector

        conn = DynamicAIConnector()
        assert conn.name == "🤖 Dynamic AI Scraper"
