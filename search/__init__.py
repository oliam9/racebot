"""
Search-Fallback Module — discovers and extracts motorsport data
when no dedicated connector exists or a connector returns incomplete data.
"""

from .client import SearchClient, SearchResult
from .domain_trust import DomainTrustModel, DomainTier
from .query_gen import QueryGenerator
from .ranking import ResultRanker
from .extractor import PageExtractor
from .orchestrator import SearchFallback, SearchOutput

__all__ = [
    "SearchClient",
    "SearchResult",
    "DomainTrustModel",
    "DomainTier",
    "QueryGenerator",
    "ResultRanker",
    "PageExtractor",
    "SearchFallback",
    "SearchOutput",
]
