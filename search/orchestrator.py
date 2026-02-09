"""
Search-Fallback Orchestrator.

Ties together SearchClient, DomainTrustModel, QueryGenerator,
ResultRanker, and PageExtractor into a single workflow that:

  1. Runs 3-pass search against a search API
  2. Ranks and selects URLs
  3. Fetches and extracts draft events/sessions
  4. Produces a SearchOutput with provenance + warnings

Used when no dedicated connector exists, or when a connector
returns incomplete data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

from models.schema import Event, Session, Venue, Source, Series
from models.enums import SessionType, SessionStatus, SeriesCategory
from validators.timezone_utils import infer_timezone_from_location

from .client import SearchClient, SearchResult, SearchProvenance
from .domain_trust import DomainTrustModel, DomainTier
from .query_gen import QueryGenerator, SearchQuery
from .ranking import ResultRanker, RankedResult
from .extractor import (
    PageExtractor,
    DraftEvent,
    DraftSession,
    ExtractionWarning,
)


@dataclass
class CandidatePage:
    """A selected page with scoring metadata."""

    url: str
    title: str
    tier: str
    score: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class MissingField:
    """Record of a field that could not be filled."""

    event_name: str
    field_name: str
    reason: str


@dataclass
class SearchOutput:
    """
    Complete output of the search-fallback module.

    Feeds the Draft Review UI.
    """

    candidate_event_pages: List[CandidatePage] = field(default_factory=list)
    extracted_draft: Optional[Series] = None
    missing_fields: List[MissingField] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    provenance: List[SearchProvenance] = field(default_factory=list)

    # Stats
    total_queries: int = 0
    total_pages_fetched: int = 0


class SearchFallback:
    """
    Main orchestrator for the search-fallback module.

    Usage:
        fb = SearchFallback(
            search_client=SerpAPIClient(api_key="..."),
            series_name="IMSA",
            series_id="imsa",
            season_year=2026,
            category="ENDURANCE",
        )
        output = fb.run()
    """

    def __init__(
        self,
        search_client: SearchClient,
        series_name: str,
        series_id: str,
        season_year: int,
        category: str = "OTHER",
    ):
        self._client = search_client
        self._series_name = series_name
        self._series_id = series_id
        self._season = season_year
        self._category = category

        self._trust = DomainTrustModel(series_id=series_id)
        self._qgen = QueryGenerator(
            series_name=series_name,
            season_year=season_year,
            trust_model=self._trust,
            category=category,
        )
        self._ranker = ResultRanker(trust_model=self._trust)
        self._extractor = PageExtractor()

        self._output = SearchOutput()

    def run(
        self,
        on_status=None,  # callback(str) for UI progress
    ) -> SearchOutput:
        """
        Execute the full 3-pass search + extraction pipeline.
        """
        # ----------------------------------------------------------
        # Pass 1 — discover schedule page
        # ----------------------------------------------------------
        if on_status:
            on_status("Pass 1: Discovering season schedule…")

        schedule_queries = self._qgen.pass1_schedule_queries()
        schedule_results = self._run_queries(schedule_queries)

        ranked = self._ranker.rank(
            schedule_results,
            self._series_name,
            self._season,
        )
        selected, sel_warnings = self._ranker.select_urls(ranked)
        self._output.warnings.extend(sel_warnings)

        for r in selected:
            self._output.candidate_event_pages.append(
                CandidatePage(
                    url=r.result.url,
                    title=r.result.title,
                    tier=r.tier.value,
                    score=r.score,
                    reasons=r.reasons,
                )
            )

        # Extract events from schedule pages
        draft_events: List[DraftEvent] = []
        for sel in selected:
            if on_status:
                on_status(f"Extracting: {sel.result.title[:50]}…")

            try:
                events, warnings = self._extractor.extract_schedule_page(
                    sel.result.url, self._series_name, self._season, sel.tier
                )
                draft_events.extend(events)
                self._output.total_pages_fetched += 1
                for w in warnings:
                    self._output.warnings.append(
                        f"[{w.severity}] {w.field}: {w.message}"
                    )
            except Exception as e:
                self._output.warnings.append(
                    f"Failed to extract {sel.result.url}: {str(e)}"
                )

        # Deduplicate events
        draft_events = self._deduplicate_events(draft_events)

        # ----------------------------------------------------------
        # Pass 2 — per-event detail page discovery
        # ----------------------------------------------------------
        if on_status:
            on_status("Pass 2: Finding event detail pages…")

        for de in draft_events:
            event_queries = self._qgen.pass2_event_queries(
                de.name, de.venue_name
            )
            event_results = self._run_queries(event_queries, max_per_query=5)

            ranked_event = self._ranker.rank(
                event_results,
                self._series_name,
                self._season,
                event_name=de.name,
            )
            sel_event, evt_warnings = self._ranker.select_urls(
                ranked_event, max_tier1=2, max_tier2=1
            )
            self._output.warnings.extend(evt_warnings)

            for sel in sel_event:
                self._output.candidate_event_pages.append(
                    CandidatePage(
                        url=sel.result.url,
                        title=sel.result.title,
                        tier=sel.tier.value,
                        score=sel.score,
                        reasons=sel.reasons,
                    )
                )

            # Extract sessions from event pages
            for sel in sel_event:
                if on_status:
                    on_status(f"Extracting sessions: {de.name[:40]}…")

                try:
                    sessions, s_warnings = self._extractor.extract_event_page(
                        sel.result.url, de.name, self._season, sel.tier
                    )
                    # Merge sessions into the draft event
                    if sessions:
                        de.sessions = sessions
                    self._output.total_pages_fetched += 1
                    for w in s_warnings:
                        self._output.warnings.append(
                            f"[{w.severity}] {w.field}: {w.message}"
                        )
                except Exception as e:
                    self._output.warnings.append(
                        f"Failed to extract sessions from {sel.result.url}: {e}"
                    )

                # Stop once we have sessions for this event
                if de.sessions:
                    break

        # ----------------------------------------------------------
        # Pass 3 — fill missing session times
        # ----------------------------------------------------------
        if on_status:
            on_status("Pass 3: Resolving missing session times…")

        for de in draft_events:
            missing_sessions = [
                s for s in de.sessions if not s.start_time
            ]
            if not de.sessions or missing_sessions:
                queries_p3 = self._qgen.pass3_session_queries(de.name)
                p3_results = self._run_queries(queries_p3, max_per_query=3)

                if p3_results:
                    ranked_p3 = self._ranker.rank(
                        p3_results,
                        self._series_name,
                        self._season,
                        event_name=de.name,
                    )
                    sel_p3, _ = self._ranker.select_urls(
                        ranked_p3, max_tier1=1, max_tier2=1
                    )

                    for sel in sel_p3:
                        try:
                            sessions, _ = self._extractor.extract_event_page(
                                sel.result.url, de.name, self._season, sel.tier
                            )
                            if sessions and len(sessions) > len(de.sessions):
                                de.sessions = sessions
                                self._output.total_pages_fetched += 1
                            break
                        except Exception:
                            pass

        # ----------------------------------------------------------
        # Convert drafts → Series
        # ----------------------------------------------------------
        if on_status:
            on_status("Building draft series…")

        series = self._build_series(draft_events)
        self._output.extracted_draft = series
        self._output.total_queries = len(
            [p for p in self._output.provenance]
        )

        # Record missing fields
        for event in series.events:
            if not event.sessions:
                self._output.missing_fields.append(
                    MissingField(
                        event_name=event.name,
                        field_name="sessions",
                        reason="No sessions found",
                    )
                )
            for s in event.sessions:
                if s.status == SessionStatus.TBD:
                    self._output.missing_fields.append(
                        MissingField(
                            event_name=event.name,
                            field_name=f"session.{s.name}.start",
                            reason="Session time not found — TBC",
                        )
                    )

        return self._output

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_queries(
        self,
        queries: List[SearchQuery],
        max_per_query: int = 10,
    ) -> List[SearchResult]:
        """Run a batch of queries, collect all results, record provenance."""
        all_results: List[SearchResult] = []
        seen_urls: set = set()

        for q in queries:
            try:
                results = self._client.search(
                    query=q.query, count=max_per_query
                )
            except Exception as e:
                self._output.warnings.append(
                    f"Search query failed: '{q.query}': {e}"
                )
                continue

            # Record provenance
            prov = SearchProvenance(
                query=q.query,
                provider=self._client.provider_name,
                result_count=len(results),
                chosen_urls=[r.url for r in results[:3]],
                scoring_reasons=[f"pass={q.pass_number}, purpose={q.purpose}"],
            )
            self._output.provenance.append(prov)

            for r in results:
                if r.url not in seen_urls:
                    all_results.append(r)
                    seen_urls.add(r.url)

        return all_results

    def _deduplicate_events(
        self, drafts: List[DraftEvent]
    ) -> List[DraftEvent]:
        """Remove duplicate events by name similarity."""
        unique: List[DraftEvent] = []
        seen_names: set = set()

        for de in drafts:
            simplified = de.name.lower().strip()
            if simplified not in seen_names:
                seen_names.add(simplified)
                unique.append(de)

        return unique

    def _build_series(self, drafts: List[DraftEvent]) -> Series:
        """Convert DraftEvents into a proper Series with Events."""
        events: List[Event] = []

        for de in drafts:
            sessions = self._convert_sessions(de.sessions, de.source_url)

            # Venue
            timezone = "UTC"
            inferred = True
            if de.city and de.country:
                tz, inf = infer_timezone_from_location(
                    country=de.country, city=de.city
                )
                if tz:
                    timezone = tz
                    inferred = inf

            venue = Venue(
                circuit=de.venue_name,
                city=de.city,
                region=de.region,
                country=de.country or "Unknown",
                timezone=timezone,
                inferred_timezone=inferred,
            )

            source = Source(
                url=de.source_url,
                provider_name=f"search_fallback ({de.source_tier})",
                retrieved_at=de.retrieved_at or datetime.utcnow(),
            )

            start = de.start_date or date(self._season, 1, 1)
            end = de.end_date or start

            event_id = f"{self._series_id}_{self._season}_{_slugify(de.name)}"

            event = Event(
                event_id=event_id,
                series_id=self._series_id,
                name=de.name,
                start_date=start,
                end_date=end,
                venue=venue,
                sessions=sessions,
                sources=[source],
                last_verified_at=de.retrieved_at,
            )
            events.append(event)

        events.sort(key=lambda e: e.start_date)

        try:
            cat = SeriesCategory(self._category.upper())
        except ValueError:
            cat = SeriesCategory.OTHER

        return Series(
            series_id=self._series_id,
            name=self._series_name,
            season=self._season,
            category=cat,
            events=events,
        )

    def _convert_sessions(
        self,
        drafts: List[DraftSession],
        fallback_url: str,
    ) -> List[Session]:
        """Convert DraftSessions into proper Sessions."""
        sessions: List[Session] = []

        for ds in drafts:
            start_iso = None
            if ds.start_time and ds.date:
                start_iso = self._build_iso_time(
                    ds.date, ds.start_time, ds.timezone_abbrev
                )

            end_iso = None
            if ds.end_time and ds.date:
                end_iso = self._build_iso_time(
                    ds.date, ds.end_time, ds.timezone_abbrev
                )

            status = ds.status
            if not start_iso:
                status = SessionStatus.TBD

            session_id = _slugify(ds.name)

            sessions.append(
                Session(
                    session_id=session_id,
                    type=ds.session_type,
                    name=ds.name,
                    start=start_iso,
                    end=end_iso,
                    status=status,
                )
            )

        return sessions

    @staticmethod
    def _build_iso_time(
        d: date,
        time_str: str,
        tz_abbrev: Optional[str],
    ) -> Optional[str]:
        """Convert date + time string → ISO-8601 with offset."""
        import re

        m = re.match(r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?", time_str)
        if not m:
            return None

        hour = int(m.group(1))
        minute = int(m.group(2))
        ampm = (m.group(3) or "").upper()

        if ampm == "PM" and hour != 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0

        offsets = {
            "ET": "-05:00", "EST": "-05:00", "EDT": "-04:00",
            "CT": "-06:00", "CST": "-06:00", "CDT": "-05:00",
            "MT": "-07:00", "MST": "-07:00", "MDT": "-06:00",
            "PT": "-08:00", "PST": "-08:00", "PDT": "-07:00",
            "CET": "+01:00", "CEST": "+02:00",
            "BST": "+01:00", "GMT": "+00:00",
            "AEST": "+10:00", "AEDT": "+11:00",
            "JST": "+09:00",
        }
        offset = offsets.get(tz_abbrev or "", "+00:00")

        return f"{d.isoformat()}T{hour:02d}:{minute:02d}:00{offset}"


def _slugify(text: str) -> str:
    """Make a slug from text."""
    import re

    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
