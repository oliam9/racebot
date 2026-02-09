"""
Result Ranking — score, filter, and select the best URLs to scrape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Set, Tuple

from .client import SearchResult, SearchProvenance
from .domain_trust import DomainTrustModel, DomainTier


@dataclass
class RankedResult:
    """A search result with scoring metadata."""

    result: SearchResult
    tier: DomainTier
    score: float
    reasons: List[str] = field(default_factory=list)


class ResultRanker:
    """
    Rank and select the best search results.

    Scoring:
      - Domain tier:   Tier1 +100, Tier2 +40, Unknown +10
      - Query match:   event_name in title/snippet +30
      - Year match:    season year in title/snippet +20
      - Series match:  series name in title/snippet +15
      - Freshness:     recent result +10
    """

    TIER_SCORES = {
        DomainTier.TIER1: 100,
        DomainTier.TIER2: 40,
        DomainTier.UNKNOWN: 10,
    }

    def __init__(self, trust_model: DomainTrustModel):
        self._trust = trust_model

    def rank(
        self,
        results: List[SearchResult],
        series_name: str,
        season_year: int,
        event_name: Optional[str] = None,
    ) -> List[RankedResult]:
        """
        Score, filter denylisted, return sorted list (best first).
        """
        ranked: List[RankedResult] = []

        for r in results:
            tier = self._trust.classify(r.url)

            # Discard denylisted
            if tier == DomainTier.DENY:
                continue

            score = 0.0
            reasons: List[str] = []

            # Domain tier
            tier_score = self.TIER_SCORES.get(tier, 0)
            score += tier_score
            reasons.append(f"domain={tier.value}(+{tier_score})")

            # Text to search in
            text = f"{r.title} {r.snippet}".lower()

            # Event name match
            if event_name and event_name.lower() in text:
                score += 30
                reasons.append("event_name_match(+30)")

            # Year match
            if str(season_year) in text:
                score += 20
                reasons.append("year_match(+20)")

            # Series match
            if series_name.lower() in text:
                score += 15
                reasons.append("series_match(+15)")

            # Keywords: schedule / timetable / sessions
            schedule_kws = ["schedule", "timetable", "sessions", "calendar"]
            if any(kw in text for kw in schedule_kws):
                score += 10
                reasons.append("schedule_kw(+10)")

            # Freshness
            if r.published_at:
                age_days = (datetime.utcnow() - r.published_at).days
                if age_days < 30:
                    score += 10
                    reasons.append("fresh(+10)")

            ranked.append(
                RankedResult(result=r, tier=tier, score=score, reasons=reasons)
            )

        ranked.sort(key=lambda x: x.score, reverse=True)
        return ranked

    def select_urls(
        self,
        ranked: List[RankedResult],
        max_tier1: int = 3,
        max_tier2: int = 2,
    ) -> Tuple[List[RankedResult], List[str]]:
        """
        Select top URLs to fetch.

        Returns (selected_results, warnings)
        """
        selected: List[RankedResult] = []
        warnings: List[str] = []
        seen_domains: Set[str] = set()

        tier1_count = 0
        tier2_count = 0

        for r in ranked:
            domain = DomainTrustModel._extract_domain(r.result.url)
            if domain in seen_domains:
                continue

            if r.tier == DomainTier.TIER1 and tier1_count < max_tier1:
                selected.append(r)
                seen_domains.add(domain)
                tier1_count += 1
            elif r.tier == DomainTier.TIER2 and tier2_count < max_tier2:
                selected.append(r)
                seen_domains.add(domain)
                tier2_count += 1
                warnings.append(
                    f"Using Tier-2 source: {domain} — data may be less authoritative"
                )
            elif r.tier == DomainTier.UNKNOWN and tier1_count == 0 and tier2_count < max_tier2:
                # Only use unknown domains if we have nothing better
                selected.append(r)
                seen_domains.add(domain)
                tier2_count += 1
                warnings.append(
                    f"Using unverified source: {domain} — manual review recommended"
                )

            if tier1_count >= max_tier1 and tier2_count >= max_tier2:
                break

        if tier1_count == 0:
            warnings.insert(
                0, "⚠ No authoritative (Tier-1) sources found — data requires careful review"
            )

        return selected, warnings

    def build_provenance(
        self,
        query: str,
        provider: str,
        selected: List[RankedResult],
    ) -> SearchProvenance:
        """Build provenance record for this search pass."""
        return SearchProvenance(
            query=query,
            provider=provider,
            result_count=len(selected),
            chosen_urls=[r.result.url for r in selected],
            scoring_reasons=[
                f"{r.result.url}: {', '.join(r.reasons)}" for r in selected
            ],
        )
