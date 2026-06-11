"""Mapping helpers from evidence bundles to legacy retrieval result fields."""

from __future__ import annotations

from packages.agent_contracts import (
    ArticleContract,
    EvidenceBundleContract,
    RetrievalResultContract,
)


def retrieval_results_from_evidence_bundle(
    bundle: EvidenceBundleContract,
    *,
    max_results: int | None = None,
) -> list[RetrievalResultContract]:
    """Convert bundle papers into legacy-compatible retrieval results."""
    papers = bundle.papers[: max_results or len(bundle.papers)]
    return [
        RetrievalResultContract(
            query=bundle.request.query,
            score=paper.relevance_score,
            content=paper.abstract or paper.title,
            article=ArticleContract(
                title=paper.title,
                authors=paper.authors,
                journal=paper.venue,
                year=paper.year or 0,
                abstract=paper.abstract,
            ),
        )
        for paper in papers
    ]


def evidence_bundle_ids(bundle: EvidenceBundleContract) -> list[str]:
    """Return the single bundle id as a list for contract linkage fields."""
    return [bundle.bundle_id] if bundle.bundle_id else []


def literature_query_ids(bundle: EvidenceBundleContract) -> list[str]:
    """Return the single query id as a list for contract linkage fields."""
    return [bundle.query_id] if bundle.query_id else []


__all__ = [
    "evidence_bundle_ids",
    "literature_query_ids",
    "retrieval_results_from_evidence_bundle",
]
