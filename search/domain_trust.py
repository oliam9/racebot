"""
Domain Trust Model — tiered allowlist/denylist per series.

Tier 1 = authoritative (official championship, circuit, timing partners)
Tier 2 = secondary   (reputable outlets — fill gaps, never override Tier 1)
Deny   = forums, scraped repost sites, spam
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse


class DomainTier(str, Enum):
    TIER1 = "tier1"
    TIER2 = "tier2"
    DENY = "deny"
    UNKNOWN = "unknown"


@dataclass
class DomainTrustConfig:
    """Trust configuration for a single series."""

    tier1: Set[str] = field(default_factory=set)
    tier2: Set[str] = field(default_factory=set)
    deny: Set[str] = field(default_factory=set)

    # Optional: official schedule URL known for this series
    official_schedule_url: Optional[str] = None


# ------------------------------------------------------------------
# Built-in configurations
# ------------------------------------------------------------------

# Global denylist patterns — applies to all series
GLOBAL_DENYLIST: Set[str] = {
    "reddit.com",
    "forum.motorsport.com",
    "forums.autosport.com",
    "racefans.net/forum",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "pinterest.com",
    "youtube.com",
    "quora.com",
    "answers.yahoo.com",
    "wikipedia.org",  # useful context but not a scheduling source
    "fandom.com",
}

# Global Tier-2 — reputable outlets accepted across all series
GLOBAL_TIER2: Set[str] = {
    "motorsport.com",
    "autosport.com",
    "racer.com",
    "motorsportweek.com",
    "the-race.com",
    "racingamerica.com",
    "sportscar365.com",
    "dailysportscar.com",
    "formula1.com",
    "motorsportstats.com",
}

# Per-series built-in configs
SERIES_DEFAULTS: Dict[str, DomainTrustConfig] = {
    "indycar": DomainTrustConfig(
        tier1={
            "indycar.com",
            "indianapolismotorspeedway.com",
        },
        official_schedule_url="https://www.indycar.com/schedule",
    ),
    "imsa": DomainTrustConfig(
        tier1={
            "imsa.com",
        },
        official_schedule_url="https://www.imsa.com/weathertech/schedule/",
    ),
    "wec": DomainTrustConfig(
        tier1={
            "fiawec.com",
            "fia.com",
            "24h-lemans.com",
        },
        official_schedule_url="https://www.fiawec.com/en/season-calendar",
    ),
    "motogp": DomainTrustConfig(
        tier1={
            "motogp.com",
        },
        official_schedule_url="https://www.motogp.com/en/calendar",
    ),
    "f1": DomainTrustConfig(
        tier1={
            "formula1.com",
            "fia.com",
        },
        official_schedule_url="https://www.formula1.com/en/racing",
    ),
    "wrc": DomainTrustConfig(
        tier1={
            "wrc.com",
            "fia.com",
        },
        official_schedule_url="https://www.wrc.com/en/calendar/",
    ),
    "nascar": DomainTrustConfig(
        tier1={
            "nascar.com",
        },
        official_schedule_url="https://www.nascar.com/nascar-cup-series/schedule/",
    ),
    "v8supercars": DomainTrustConfig(
        tier1={
            "supercars.com",
        },
    ),
    "super_formula": DomainTrustConfig(
        tier1={
            "superformula.net",
        },
    ),
    "super_gt": DomainTrustConfig(
        tier1={
            "supergt.net",
        },
    ),
}


class DomainTrustModel:
    """
    Classify domains into tiers for a given series.

    Resolution order:
      1. Series-specific config (tier1 > tier2 > deny)
      2. Global denylist
      3. Global tier-2
      4. Unknown
    """

    def __init__(
        self,
        series_id: Optional[str] = None,
        extra_tier1: Optional[Set[str]] = None,
        extra_tier2: Optional[Set[str]] = None,
        extra_deny: Optional[Set[str]] = None,
    ):
        self._series_id = series_id
        self._config = DomainTrustConfig()

        # Load defaults
        if series_id and series_id in SERIES_DEFAULTS:
            defaults = SERIES_DEFAULTS[series_id]
            self._config.tier1 = set(defaults.tier1)
            self._config.tier2 = set(defaults.tier2)
            self._config.deny = set(defaults.deny)
            self._config.official_schedule_url = defaults.official_schedule_url

        # Merge extras
        if extra_tier1:
            self._config.tier1 |= extra_tier1
        if extra_tier2:
            self._config.tier2 |= extra_tier2
        if extra_deny:
            self._config.deny |= extra_deny

    @property
    def official_schedule_url(self) -> Optional[str]:
        return self._config.official_schedule_url

    @property
    def tier1_domains(self) -> Set[str]:
        return self._config.tier1

    def classify(self, url: str) -> DomainTier:
        """Classify a URL's domain into a tier."""
        domain = self._extract_domain(url)
        if not domain:
            return DomainTier.DENY

        # Series-specific first
        if self._domain_matches(domain, self._config.tier1):
            return DomainTier.TIER1
        if self._domain_matches(domain, self._config.deny):
            return DomainTier.DENY

        # Global denylist
        if self._domain_matches(domain, GLOBAL_DENYLIST):
            return DomainTier.DENY

        # Series-specific tier2
        if self._domain_matches(domain, self._config.tier2):
            return DomainTier.TIER2

        # Global tier2
        if self._domain_matches(domain, GLOBAL_TIER2):
            return DomainTier.TIER2

        return DomainTier.UNKNOWN

    def is_allowed(self, url: str) -> bool:
        """Return True if URL is not denylisted."""
        return self.classify(url) != DomainTier.DENY

    # ------------------------------------------------------------------

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Get root domain from URL."""
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            # strip www.
            if host.startswith("www."):
                host = host[4:]
            return host.lower()
        except Exception:
            return ""

    @staticmethod
    def _domain_matches(domain: str, domain_set: Set[str]) -> bool:
        """
        Check if domain matches any entry in the set.
        Supports suffix matching (e.g., "sub.indycar.com" matches "indycar.com").
        """
        for d in domain_set:
            if domain == d or domain.endswith("." + d):
                return True
        return False
