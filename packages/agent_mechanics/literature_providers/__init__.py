"""Literature search provider adapters."""

from __future__ import annotations

from collections.abc import Callable

from packages.agent_contracts import LiteratureProviderName, SearchRequestContract

from . import arxiv, crossref, europe_pmc, openalex, semantic_scholar
from .common import ProviderSearchResult


ProviderSearchFunction = Callable[[SearchRequestContract], ProviderSearchResult]

PROVIDER_SEARCHERS: dict[LiteratureProviderName, ProviderSearchFunction] = {
    "arxiv": arxiv.search,
    "crossref": crossref.search,
    "europe_pmc": europe_pmc.search,
    "openalex": openalex.search,
    "semantic_scholar": semantic_scholar.search,
}


__all__ = [
    "PROVIDER_SEARCHERS",
    "ProviderSearchFunction",
    "ProviderSearchResult",
]
