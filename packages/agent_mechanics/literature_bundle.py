"""Deduplication, ranking, and evidence bundle construction helpers."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from packages.agent_contracts import (
    EvidenceBundleContract,
    EvidenceRetrievalMetadataContract,
    LiteratureProviderName,
    PaperCandidateContract,
    SearchProviderReceiptContract,
    SearchRequestContract,
)


_TITLE_NORMALIZE_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def build_evidence_bundle(
    request: SearchRequestContract,
    candidates: list[PaperCandidateContract],
    provider_receipts: list[SearchProviderReceiptContract],
) -> EvidenceBundleContract:
    """Build a traceable evidence bundle from raw provider candidates."""
    deduped = dedupe_candidates(candidates)
    ranked = rank_candidates(deduped)[: request.filters.max_results]
    providers_attempted = [receipt.provider for receipt in provider_receipts]
    providers_succeeded = [receipt.provider for receipt in provider_receipts if receipt.status == "succeeded"]
    if not providers_succeeded:
        status = "blocked"
        reason = "All requested literature providers failed, were skipped, or returned no usable call."
    elif len(providers_succeeded) == len(providers_attempted):
        status = "succeeded"
        reason = "All attempted literature providers succeeded."
    else:
        status = "partial"
        reason = "At least one literature provider succeeded and at least one did not."
    metadata = EvidenceRetrievalMetadataContract(
        status=status,
        reason=reason,
        created_at=datetime.now(UTC),
        providers_attempted=providers_attempted,
        providers_succeeded=providers_succeeded,
        total_raw_results=len(candidates),
        total_deduped_results=len(ranked),
        verified_count=0,
        unverified_count=0,
        pending_count=0,
    )
    query_id = request.query_id or stable_query_id(request)
    return EvidenceBundleContract(
        bundle_id=f"bundle-{query_id}",
        query_id=query_id,
        request=request,
        provider_receipts=provider_receipts,
        papers=ranked,
        verified_papers=[],
        synthesized_findings=[],
        retrieval_metadata=metadata,
    )


def dedupe_candidates(candidates: list[PaperCandidateContract]) -> list[PaperCandidateContract]:
    """Deduplicate candidates by DOI, arXiv ID, PMID/PMCID, then normalized title."""
    merged: dict[str, PaperCandidateContract] = {}
    for candidate in candidates:
        key = candidate_key(candidate)
        if key not in merged:
            merged[key] = candidate
        else:
            merged[key] = merge_candidates(merged[key], candidate)
    return list(merged.values())


def rank_candidates(candidates: list[PaperCandidateContract]) -> list[PaperCandidateContract]:
    """Rank candidates by provider relevance, citation count, recency, and metadata quality."""
    return sorted(candidates, key=candidate_rank_key, reverse=True)


def merge_candidates(
    primary: PaperCandidateContract,
    secondary: PaperCandidateContract,
) -> PaperCandidateContract:
    """Merge two provider records for the same paper."""
    provider_sources = _merge_unique(primary.provider_sources, secondary.provider_sources)
    raw_provider_ids = dict(primary.raw_provider_ids)
    raw_provider_ids.update(secondary.raw_provider_ids)
    return primary.model_copy(
        update={
            "paper_id": primary.paper_id or secondary.paper_id,
            "title": _prefer_text(primary.title, secondary.title),
            "authors": primary.authors or secondary.authors,
            "year": primary.year or secondary.year,
            "venue": _prefer_text(primary.venue, secondary.venue),
            "doi": primary.doi or secondary.doi,
            "arxiv_id": primary.arxiv_id or secondary.arxiv_id,
            "pmid": primary.pmid or secondary.pmid,
            "pmcid": primary.pmcid or secondary.pmcid,
            "url": _prefer_text(primary.url, secondary.url),
            "open_access_url": _prefer_text(primary.open_access_url, secondary.open_access_url),
            "abstract": _prefer_longer(primary.abstract, secondary.abstract),
            "provider_sources": provider_sources,
            "raw_provider_ids": raw_provider_ids,
            "citation_count": max(primary.citation_count or 0, secondary.citation_count or 0),
            "relevance_score": max(primary.relevance_score, secondary.relevance_score),
        }
    )


def candidate_key(candidate: PaperCandidateContract) -> str:
    """Return the canonical deduplication key for a paper candidate."""
    if candidate.doi:
        return f"doi:{candidate.doi.lower()}"
    if candidate.arxiv_id:
        return f"arxiv:{candidate.arxiv_id.lower()}"
    if candidate.pmid:
        return f"pmid:{candidate.pmid}"
    if candidate.pmcid:
        return f"pmcid:{candidate.pmcid.lower()}"
    normalized_title = normalize_title(candidate.title)
    if normalized_title:
        digest = hashlib.sha1(normalized_title.encode(), usedforsecurity=False).hexdigest()[:16]
        return f"title:{digest}"
    return candidate.paper_id or "unknown"


def candidate_rank_key(candidate: PaperCandidateContract) -> tuple[float, int, int, int, int]:
    """Return a stable ranking tuple for one candidate."""
    citation_count = candidate.citation_count or 0
    year = candidate.year or 0
    identifier_bonus = int(bool(candidate.doi or candidate.arxiv_id or candidate.pmid or candidate.pmcid))
    abstract_bonus = int(bool(candidate.abstract))
    return (
        candidate.relevance_score,
        citation_count,
        year,
        identifier_bonus,
        abstract_bonus,
    )


def stable_query_id(request: SearchRequestContract) -> str:
    """Create a deterministic short query id from the request content."""
    digest = hashlib.sha1(
        f"{request.goal}\n{request.query}\n{request.query_type}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:12]
    return f"q-{digest}"


def normalize_title(value: str) -> str:
    """Normalize titles for deduplication."""
    value = _TITLE_NORMALIZE_RE.sub(" ", value.lower())
    return _WHITESPACE_RE.sub(" ", value).strip()


def _merge_unique(
    left: list[LiteratureProviderName],
    right: list[LiteratureProviderName],
) -> list[LiteratureProviderName]:
    merged: list[LiteratureProviderName] = []
    for item in [*left, *right]:
        if item not in merged:
            merged.append(item)
    return merged


def _prefer_text(left: str, right: str) -> str:
    return left or right


def _prefer_longer(left: str, right: str) -> str:
    return left if len(left) >= len(right) else right


__all__ = [
    "build_evidence_bundle",
    "candidate_key",
    "candidate_rank_key",
    "dedupe_candidates",
    "merge_candidates",
    "normalize_title",
    "rank_candidates",
    "stable_query_id",
]
