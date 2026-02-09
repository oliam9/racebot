"""
Tests for the search-fallback module.
"""

import pytest
from datetime import datetime, date
from unittest.mock import patch, MagicMock

from search.client import SearchResult, SearchProvenance, SerpAPIClient
from search.domain_trust import DomainTrustModel, DomainTier, GLOBAL_DENYLIST
from search.query_gen import QueryGenerator, SearchQuery
from search.ranking import ResultRanker, RankedResult
from search.extractor import PageExtractor, DraftEvent, DraftSession
from search.orchestrator import SearchFallback, SearchOutput, _slugify


# ===================================================================
# Domain Trust Model
# ===================================================================


class TestDomainTrustModel:
    """Tests for DomainTrustModel."""

    def test_tier1_official_domain(self):
        model = DomainTrustModel(series_id="indycar")
        assert model.classify("https://www.indycar.com/schedule") == DomainTier.TIER1

    def test_tier1_subdomain(self):
        model = DomainTrustModel(series_id="indycar")
        assert model.classify("https://news.indycar.com/2026") == DomainTier.TIER1

    def test_tier2_global(self):
        model = DomainTrustModel(series_id="indycar")
        assert model.classify("https://motorsport.com/indycar/2026") == DomainTier.TIER2

    def test_deny_reddit(self):
        model = DomainTrustModel(series_id="indycar")
        assert model.classify("https://reddit.com/r/indycar") == DomainTier.DENY

    def test_deny_social(self):
        model = DomainTrustModel()
        for domain in ["twitter.com", "facebook.com", "youtube.com"]:
            assert model.classify(f"https://{domain}/something") == DomainTier.DENY

    def test_unknown_domain(self):
        model = DomainTrustModel(series_id="indycar")
        assert model.classify("https://randomsite.xyz/stuff") == DomainTier.UNKNOWN

    def test_is_allowed(self):
        model = DomainTrustModel(series_id="imsa")
        assert model.is_allowed("https://imsa.com/schedule") == True
        assert model.is_allowed("https://reddit.com/r/imsa") == False

    def test_extra_tier1(self):
        model = DomainTrustModel(
            series_id="indycar",
            extra_tier1={"mytrack.com"},
        )
        assert model.classify("https://mytrack.com") == DomainTier.TIER1

    def test_official_schedule_url(self):
        model = DomainTrustModel(series_id="f1")
        assert model.official_schedule_url is not None
        assert "formula1.com" in model.official_schedule_url

    def test_wec_config(self):
        model = DomainTrustModel(series_id="wec")
        assert model.classify("https://fiawec.com/season") == DomainTier.TIER1

    def test_empty_url(self):
        model = DomainTrustModel()
        assert model.classify("") == DomainTier.DENY


# ===================================================================
# Query Generator
# ===================================================================


class TestQueryGenerator:
    """Tests for QueryGenerator."""

    def setup_method(self):
        self.trust = DomainTrustModel(series_id="imsa")
        self.qgen = QueryGenerator(
            series_name="IMSA WeatherTech",
            season_year=2026,
            trust_model=self.trust,
            category="endurance",
        )

    def test_pass1_queries_count(self):
        queries = self.qgen.pass1_schedule_queries()
        assert len(queries) >= 3
        assert all(q.pass_number == 1 for q in queries)

    def test_pass1_contains_series_name(self):
        queries = self.qgen.pass1_schedule_queries()
        query_texts = [q.query for q in queries]
        assert any("IMSA" in q for q in query_texts)

    def test_pass1_site_restriction(self):
        queries = self.qgen.pass1_schedule_queries()
        site_restricted = [q for q in queries if q.site_restriction]
        assert len(site_restricted) > 0
        assert any("imsa.com" in q.site_restriction for q in site_restricted)

    def test_pass2_event_queries(self):
        queries = self.qgen.pass2_event_queries("Rolex 24 at Daytona")
        assert len(queries) >= 3
        assert all(q.pass_number == 2 for q in queries)
        assert any("Rolex 24" in q.query for q in queries)

    def test_pass3_session_queries(self):
        queries = self.qgen.pass3_session_queries(
            "Rolex 24 at Daytona", "Practice 1"
        )
        assert len(queries) >= 2
        assert all(q.pass_number == 3 for q in queries)

    def test_pass3_endurance_synonyms(self):
        queries = self.qgen.pass3_session_queries("Rolex 24 at Daytona")
        query_texts = " ".join(q.query for q in queries)
        assert any(
            syn in query_texts
            for syn in ["Hyperpole", "FP1", "warm up"]
        )


# ===================================================================
# Result Ranker
# ===================================================================


class TestResultRanker:
    """Tests for ResultRanker."""

    def setup_method(self):
        self.trust = DomainTrustModel(series_id="indycar")
        self.ranker = ResultRanker(trust_model=self.trust)

    def _make_result(self, url, title="", snippet=""):
        return SearchResult(url=url, title=title, snippet=snippet)

    def test_tier1_scores_highest(self):
        results = [
            self._make_result("https://indycar.com/schedule", "IndyCar 2026"),
            self._make_result("https://motorsport.com/indycar", "IndyCar 2026"),
            self._make_result("https://random.com/stuff"),
        ]
        ranked = self.ranker.rank(results, "IndyCar", 2026)
        assert ranked[0].tier == DomainTier.TIER1

    def test_deny_filtered_out(self):
        results = [
            self._make_result("https://reddit.com/r/indycar"),
            self._make_result("https://indycar.com/schedule"),
        ]
        ranked = self.ranker.rank(results, "IndyCar", 2026)
        urls = [r.result.url for r in ranked]
        assert "https://reddit.com/r/indycar" not in urls

    def test_year_match_bonus(self):
        results = [
            self._make_result("https://example.com/a", "Old schedule", "2024 data"),
            self._make_result("https://example.com/b", "New schedule", "2026 data"),
        ]
        ranked = self.ranker.rank(results, "IndyCar", 2026)
        assert ranked[0].result.url == "https://example.com/b"

    def test_select_urls_prefers_tier1(self):
        results = [
            self._make_result("https://indycar.com/schedule", "IndyCar 2026"),
            self._make_result("https://motorsport.com/indycar", "IndyCar news"),
        ]
        ranked = self.ranker.rank(results, "IndyCar", 2026)
        selected, warnings = self.ranker.select_urls(ranked)
        assert any(r.tier == DomainTier.TIER1 for r in selected)

    def test_select_urls_warns_on_no_tier1(self):
        results = [
            self._make_result("https://randomsite.com/indycar", "IndyCar 2026"),
        ]
        ranked = self.ranker.rank(results, "IndyCar", 2026)
        selected, warnings = self.ranker.select_urls(ranked)
        assert any("Tier-1" in w for w in warnings)

    def test_build_provenance(self):
        results = [self._make_result("https://indycar.com/schedule")]
        ranked = self.ranker.rank(results, "IndyCar", 2026)
        prov = self.ranker.build_provenance("IndyCar 2026 schedule", "serpapi", ranked)
        assert prov.query == "IndyCar 2026 schedule"
        assert prov.provider == "serpapi"
        assert len(prov.chosen_urls) > 0


# ===================================================================
# Page Extractor
# ===================================================================


class TestPageExtractor:
    """Tests for PageExtractor utility methods."""

    def setup_method(self):
        self.extractor = PageExtractor()

    def test_parse_date_range_same_month(self):
        start, end = self.extractor._parse_date_range("March 6 - 7", 2026)
        assert start == date(2026, 3, 6)
        assert end == date(2026, 3, 7)

    def test_parse_date_range_cross_month(self):
        start, end = self.extractor._parse_date_range(
            "February 27 - March 1", 2026
        )
        assert start == date(2026, 2, 27)
        assert end == date(2026, 3, 1)

    def test_parse_date_range_no_match(self):
        start, end = self.extractor._parse_date_range("no date here", 2026)
        assert start is None
        assert end is None

    def test_parse_single_date(self):
        d = self.extractor._parse_single_date("Friday, March 6", 2026)
        assert d == date(2026, 3, 6)

    def test_classify_practice(self):
        assert PageExtractor._classify_session("Practice 1") == "PRACTICE"

    def test_classify_qualifying(self):
        assert PageExtractor._classify_session("Qualifying") == "QUALIFYING"

    def test_classify_race(self):
        assert PageExtractor._classify_session("Race") == "RACE"

    def test_classify_warmup(self):
        assert PageExtractor._classify_session("Warm Up") == "WARMUP"


# ===================================================================
# Utilities
# ===================================================================


class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello_world"

    def test_special_chars(self):
        assert _slugify("Rolex 24 at Daytona!") == "rolex_24_at_daytona"


# ===================================================================
# Search Client (unit tests with mocks)
# ===================================================================


class TestSearchClient:
    """Test SearchClient caching and rate limiting."""

    def test_cache_hit(self):
        client = SerpAPIClient(api_key="test_key")
        # Pre-fill cache
        cached_results = [SearchResult(title="Cached", url="http://cached.com", snippet="")]
        cache_key = "test query::10::None"
        client._cache[cache_key] = cached_results
        client._cache_ts[cache_key] = __import__("time").time()

        results = client.search("test query", count=10)
        assert results == cached_results
        assert results[0].title == "Cached"
