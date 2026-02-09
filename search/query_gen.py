"""
Query Generator — builds search queries using a 3-pass strategy.

Pass 1: Season schedule discovery (broad)
Pass 2: Event page discovery (per event)
Pass 3: Session timing resolution (narrow, per missing field)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

from .domain_trust import DomainTrustModel


@dataclass
class SearchQuery:
    """A generated search query with metadata."""

    query: str
    pass_number: int  # 1, 2, or 3
    purpose: str  # human-readable intent
    site_restriction: Optional[str] = None  # domain to restrict to


# ------------------------------------------------------------------
# Series-specific keyword hints
# ------------------------------------------------------------------

SERIES_SYNONYMS = {
    "rally": [
        "itinerary", "stages", "SS1", "shakedown",
        "service park timetable", "leg",
    ],
    "endurance": [
        "FP1", "FP2", "FP3", "Hyperpole", "warm up",
        "race start", "formation lap",
    ],
    "openwheel": [
        "practice", "qualifying", "race", "warm up",
        "sprint", "feature race",
    ],
    "motorcycle": [
        "FP1", "FP2", "qualifying", "sprint race",
        "main race", "warm up",
    ],
}


class QueryGenerator:
    """
    Generate search queries from structured inputs
    using a 3-pass strategy.
    """

    def __init__(
        self,
        series_name: str,
        season_year: int,
        trust_model: DomainTrustModel,
        category: Optional[str] = None,
    ):
        self._series = series_name
        self._year = season_year
        self._trust = trust_model
        self._category = (category or "").lower()

    # ------------------------------------------------------------------
    # Pass 1 — season schedule discovery
    # ------------------------------------------------------------------

    def pass1_schedule_queries(self) -> List[SearchQuery]:
        """Broad queries to find the season schedule page."""
        queries: List[SearchQuery] = []

        base_queries = [
            f"{self._series} {self._year} schedule",
            f"{self._series} {self._year} calendar",
            f"{self._series} {self._year} race schedule dates",
        ]

        for q in base_queries:
            queries.append(
                SearchQuery(query=q, pass_number=1, purpose="season schedule")
            )

        # Add site-restricted queries for tier-1 domains
        for domain in self._trust.tier1_domains:
            queries.append(
                SearchQuery(
                    query=f"site:{domain} {self._year} schedule",
                    pass_number=1,
                    purpose=f"official schedule on {domain}",
                    site_restriction=domain,
                )
            )

        return queries

    # ------------------------------------------------------------------
    # Pass 2 — event page discovery
    # ------------------------------------------------------------------

    def pass2_event_queries(
        self,
        event_name: str,
        venue_name: Optional[str] = None,
        country: Optional[str] = None,
        city: Optional[str] = None,
    ) -> List[SearchQuery]:
        """Per-event queries to find the event's official page."""
        queries: List[SearchQuery] = []

        base_queries = [
            f"{event_name} {self._year} schedule sessions",
            f"{event_name} {self._year} practice qualifying race time",
            f"{event_name} {self._series} {self._year} timetable",
        ]

        for q in base_queries:
            queries.append(
                SearchQuery(
                    query=q, pass_number=2, purpose=f"event page: {event_name}"
                )
            )

        # Site-restricted on tier-1 domains
        for domain in self._trust.tier1_domains:
            queries.append(
                SearchQuery(
                    query=f'site:{domain} "{event_name}" {self._year}',
                    pass_number=2,
                    purpose=f"official event page on {domain}",
                    site_restriction=domain,
                )
            )

        # If we have a venue/circuit domain, search there too
        if venue_name:
            queries.append(
                SearchQuery(
                    query=f'"{event_name}" {self._year} "{venue_name}" schedule',
                    pass_number=2,
                    purpose=f"venue-specific schedule for {event_name}",
                )
            )

        return queries

    # ------------------------------------------------------------------
    # Pass 3 — session timing resolution
    # ------------------------------------------------------------------

    def pass3_session_queries(
        self,
        event_name: str,
        session_name: Optional[str] = None,
    ) -> List[SearchQuery]:
        """Narrow queries to fill missing session times."""
        queries: List[SearchQuery] = []

        if session_name:
            queries.append(
                SearchQuery(
                    query=f'"{event_name}" {self._year} "{session_name}" time',
                    pass_number=3,
                    purpose=f"session time: {session_name}",
                )
            )

        # Generic session timing queries
        variants = [
            f'"{event_name}" {self._year} schedule times',
            f'"{event_name}" {self._year} timetable session times',
            f'"{event_name}" {self._year} event schedule',
        ]

        for q in variants:
            queries.append(
                SearchQuery(query=q, pass_number=3, purpose="session times")
            )

        # Series-specific synonyms
        synonyms = SERIES_SYNONYMS.get(self._category, [])
        if synonyms:
            keyword_block = " OR ".join(f'"{s}"' for s in synonyms[:4])
            queries.append(
                SearchQuery(
                    query=f'"{event_name}" {self._year} ({keyword_block})',
                    pass_number=3,
                    purpose=f"series-specific session keywords",
                )
            )

        return queries

    # ------------------------------------------------------------------
    # All-in-one convenience
    # ------------------------------------------------------------------

    def all_schedule_queries(self) -> List[SearchQuery]:
        """Return Pass 1 queries (schedule discovery)."""
        return self.pass1_schedule_queries()

    def all_event_queries(
        self,
        event_name: str,
        venue_name: Optional[str] = None,
    ) -> List[SearchQuery]:
        """Return Pass 2 + Pass 3 queries for a specific event."""
        return self.pass2_event_queries(
            event_name, venue_name
        ) + self.pass3_session_queries(event_name)
