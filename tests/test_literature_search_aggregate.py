from __future__ import annotations

from packages.agent_contracts import PaperCandidateContract, SearchProviderReceiptContract, SearchRequestContract
from packages.agent_mechanics.literature_bundle import dedupe_candidates, rank_candidates
from packages.agent_mechanics.literature_providers.common import ProviderSearchResult
from packages.agent_mechanics.literature_search import resolve_provider_sequence, run_literature_search


def _request(providers=None) -> SearchRequestContract:
    return SearchRequestContract(
        query_id="q-001",
        query="ammonia synthesis catalyst",
        providers=providers or ["openalex"],
        filters={"max_results": 10},
    )


def _receipt(provider: str, status: str, count: int = 0) -> SearchProviderReceiptContract:
    return SearchProviderReceiptContract(provider=provider, status=status, result_count=count)


def test_resolve_provider_sequence_expands_auto_without_duplicates() -> None:
    providers = resolve_provider_sequence(["auto", "crossref"])

    assert providers[0:3] == ["openalex", "crossref", "europe_pmc"]
    assert providers.count("crossref") == 1
    assert "auto" not in providers


def test_dedupe_candidates_merges_provider_sources_by_doi() -> None:
    first = PaperCandidateContract(
        paper_id="doi:10.1000/example",
        title="Short title",
        doi="10.1000/example",
        provider_sources=["openalex"],
        abstract="Short.",
        citation_count=2,
    )
    second = PaperCandidateContract(
        paper_id="doi:10.1000/example",
        title="Short title",
        doi="10.1000/example",
        provider_sources=["crossref"],
        abstract="Longer abstract from another source.",
        citation_count=10,
    )

    deduped = dedupe_candidates([first, second])

    assert len(deduped) == 1
    assert deduped[0].provider_sources == ["openalex", "crossref"]
    assert deduped[0].abstract == "Longer abstract from another source."
    assert deduped[0].citation_count == 10


def test_rank_candidates_prefers_relevance_then_citations_then_year() -> None:
    low = PaperCandidateContract(title="low", relevance_score=0.1, citation_count=100, year=2026)
    high = PaperCandidateContract(title="high", relevance_score=0.9, citation_count=1, year=2020)

    ranked = rank_candidates([low, high])

    assert ranked[0].title == "high"


def test_run_literature_search_returns_partial_bundle_when_one_provider_fails() -> None:
    def openalex_search(request: SearchRequestContract) -> ProviderSearchResult:
        return ProviderSearchResult(
            candidates=[
                PaperCandidateContract(
                    paper_id="doi:10.1000/example",
                    title="Catalyst evidence",
                    doi="10.1000/example",
                    provider_sources=["openalex"],
                    relevance_score=0.5,
                )
            ],
            receipt=_receipt("openalex", "succeeded", 1),
        )

    bundle = run_literature_search(
        _request(["openalex", "crossref"]),
        provider_searchers={"openalex": openalex_search},
    )

    assert bundle.retrieval_metadata.status == "partial"
    assert bundle.retrieval_metadata.providers_succeeded == ["openalex"]
    assert [receipt.provider for receipt in bundle.provider_receipts] == ["openalex", "crossref"]
    assert bundle.provider_receipts[1].status == "skipped_missing_dependency"
    assert bundle.papers[0].title == "Catalyst evidence"


def test_run_literature_search_returns_blocked_bundle_when_no_provider_succeeds() -> None:
    def failed_search(request: SearchRequestContract) -> ProviderSearchResult:
        return ProviderSearchResult(
            candidates=[],
            receipt=_receipt("openalex", "failed_provider_error", 0),
        )

    bundle = run_literature_search(
        _request(["openalex"]),
        provider_searchers={"openalex": failed_search},
    )

    assert bundle.retrieval_metadata.status == "blocked"
    assert bundle.retrieval_metadata.providers_succeeded == []
    assert bundle.papers == []
