"""Literature search aggregate orchestration."""

from __future__ import annotations

from collections.abc import Mapping

from packages.agent_contracts import (
    EvidenceBundleContract,
    LiteratureProviderName,
    SearchRequestContract,
)

from .literature_bundle import build_evidence_bundle
from .literature_providers import PROVIDER_SEARCHERS, ProviderSearchFunction
from .literature_providers.common import ProviderMissingDependencyError, ProviderSearchResult, run_provider


DEFAULT_PROVIDER_SEQUENCE: tuple[LiteratureProviderName, ...] = (
    "openalex",
    "crossref",
    "europe_pmc",
    "semantic_scholar",
    "arxiv",
)


def run_literature_search(
    request: SearchRequestContract,
    *,
    provider_searchers: Mapping[LiteratureProviderName, ProviderSearchFunction] | None = None,
) -> EvidenceBundleContract:
    """Run the D2 multi-source literature aggregate and return an evidence bundle."""
    searchers = provider_searchers or PROVIDER_SEARCHERS
    candidates = []
    receipts = []
    for provider in resolve_provider_sequence(request.providers):
        searcher = searchers.get(provider)
        result = _missing_provider_result(provider, request) if searcher is None else searcher(request)
        candidates.extend(result.candidates)
        receipts.append(result.receipt)
    return build_evidence_bundle(request, candidates, receipts)


def resolve_provider_sequence(
    providers: list[LiteratureProviderName] | tuple[LiteratureProviderName, ...],
) -> list[LiteratureProviderName]:
    """Resolve request provider names into an ordered provider sequence."""
    if not providers or "auto" in providers:
        selected = list(DEFAULT_PROVIDER_SEQUENCE)
        selected.extend(provider for provider in providers if provider != "auto")
    else:
        selected = list(providers)

    deduped: list[LiteratureProviderName] = []
    for provider in selected:
        if provider == "auto":
            continue
        if provider not in deduped:
            deduped.append(provider)
    return deduped


def _missing_provider_result(
    provider: LiteratureProviderName,
    request: SearchRequestContract,
) -> ProviderSearchResult:
    def missing_provider(_: SearchRequestContract):
        raise ProviderMissingDependencyError(f"Literature provider `{provider}` is not available.")

    return run_provider(provider, request, missing_provider)


__all__ = [
    "DEFAULT_PROVIDER_SEQUENCE",
    "resolve_provider_sequence",
    "run_literature_search",
]
