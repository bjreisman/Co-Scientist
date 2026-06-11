"""Contracts for the literature search bridge and evidence bundles."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


LiteratureProviderName = Literal[
    "auto",
    "arxiv",
    "crossref",
    "europe_pmc",
    "openalex",
    "semantic_scholar",
    "local",
]
LiteratureQueryType = Literal[
    "broad_landscape",
    "mechanism_support",
    "novelty_scan",
    "contradiction_scan",
    "claim_verification",
    "evidence_gathering",
]
LiteratureConsumerName = Literal[
    "literature-search",
    "hypothesis-generate-literature",
    "hypothesis-full-review",
    "hypothesis-deep-verification",
    "research-overview-pipeline",
]
LiteratureProviderStatus = Literal[
    "succeeded",
    "skipped_disabled",
    "skipped_missing_dependency",
    "skipped_missing_api_key",
    "failed_rate_limited",
    "failed_timeout",
    "failed_provider_error",
    "failed_invalid_response",
]
LiteratureSearchStatus = Literal["succeeded", "partial", "blocked"]
PaperVerificationStatus = Literal["verified", "unverified", "verify_pending", "error"]
PaperVerificationMethod = Literal[
    "arxiv",
    "crossref",
    "semantic_scholar",
    "openalex",
    "europe_pmc",
    "title_fuzzy",
    "none",
]
EvidenceFindingType = Literal[
    "support",
    "contradiction",
    "gap",
    "open_question",
    "method_pattern",
]
EvidenceConfidence = Literal["high", "medium", "low"]


class LiteratureSearchFiltersContract(BaseModel):
    """Optional filters applied to a literature search request."""

    model_config = ConfigDict(extra="ignore")

    year_min: int | None = Field(default=None)
    year_max: int | None = Field(default=None)
    max_results: int = Field(default=10, ge=1)
    open_access_only: bool = Field(default=False)
    min_citations: int | None = Field(default=None, ge=0)


class SearchRequestContract(BaseModel):
    """Canonical input for one literature search bridge request."""

    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(default="")
    query_id: str = Field(default="")
    goal: str = Field(default="")
    query: str = Field(default="")
    query_type: LiteratureQueryType = Field(default="evidence_gathering")
    keywords: list[str] = Field(default_factory=list)
    providers: list[LiteratureProviderName] = Field(default_factory=lambda: ["auto"])
    filters: LiteratureSearchFiltersContract = Field(default_factory=LiteratureSearchFiltersContract)
    consumer: LiteratureConsumerName = Field(default="literature-search")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> SearchRequestContract:
        """Validate a raw search request payload."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> SearchRequestContract:
        """Load and validate one persisted search request."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


class SearchProviderReceiptContract(BaseModel):
    """Receipt for one provider attempt in a literature search request."""

    model_config = ConfigDict(extra="ignore")

    provider: LiteratureProviderName = Field(default="openalex")
    status: LiteratureProviderStatus = Field(default="failed_provider_error")
    request_hash: str = Field(default="")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    elapsed_ms: int = Field(default=0, ge=0)
    result_count: int = Field(default=0, ge=0)
    error_type: str = Field(default="")
    error_message: str = Field(default="")
    retry_count: int = Field(default=0, ge=0)
    rate_limit_observed: bool = Field(default=False)

    @classmethod
    def from_payload(cls, payload: Any) -> SearchProviderReceiptContract:
        """Validate a raw provider receipt payload."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> SearchProviderReceiptContract:
        """Load and validate one persisted provider receipt."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


class PaperCandidateContract(BaseModel):
    """Normalized candidate paper returned by one or more literature providers."""

    model_config = ConfigDict(extra="ignore")

    paper_id: str = Field(default="")
    title: str = Field(default="")
    authors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None)
    venue: str = Field(default="")
    doi: str | None = Field(default=None)
    arxiv_id: str | None = Field(default=None)
    pmid: str | None = Field(default=None)
    pmcid: str | None = Field(default=None)
    url: str = Field(default="")
    open_access_url: str = Field(default="")
    abstract: str = Field(default="")
    provider_sources: list[LiteratureProviderName] = Field(default_factory=list)
    raw_provider_ids: dict[str, str] = Field(default_factory=dict)
    citation_count: int | None = Field(default=None, ge=0)
    relevance_score: float = Field(default=0.0)

    @classmethod
    def from_payload(cls, payload: Any) -> PaperCandidateContract:
        """Validate a raw normalized candidate paper payload."""
        return cls.model_validate(payload)


class PaperVerificationContract(BaseModel):
    """Paper-existence verification outcome for one candidate paper."""

    model_config = ConfigDict(extra="ignore")

    paper_id: str = Field(default="")
    status: PaperVerificationStatus = Field(default="verify_pending")
    method: PaperVerificationMethod = Field(default="none")
    confidence: EvidenceConfidence = Field(default="low")
    reason: str = Field(default="")
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> PaperVerificationContract:
        """Validate a raw paper verification payload."""
        return cls.model_validate(payload)


class EvidenceFindingContract(BaseModel):
    """Synthesized evidence statement derived from papers in a bundle."""

    model_config = ConfigDict(extra="ignore")

    finding_id: str = Field(default="")
    type: EvidenceFindingType = Field(default="support")
    statement: str = Field(default="")
    paper_refs: list[str] = Field(default_factory=list)
    confidence: EvidenceConfidence = Field(default="low")


class EvidenceRetrievalMetadataContract(BaseModel):
    """Summary metadata for a completed evidence bundle."""

    model_config = ConfigDict(extra="ignore")

    status: LiteratureSearchStatus = Field(default="blocked")
    reason: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    providers_attempted: list[LiteratureProviderName] = Field(default_factory=list)
    providers_succeeded: list[LiteratureProviderName] = Field(default_factory=list)
    total_raw_results: int = Field(default=0, ge=0)
    total_deduped_results: int = Field(default=0, ge=0)
    verified_count: int = Field(default=0, ge=0)
    unverified_count: int = Field(default=0, ge=0)
    pending_count: int = Field(default=0, ge=0)


class EvidenceBundleContract(BaseModel):
    """Canonical evidence bundle consumed by literature-grounded skills."""

    model_config = ConfigDict(extra="ignore")

    bundle_id: str = Field(default="")
    query_id: str = Field(default="")
    request: SearchRequestContract = Field(default_factory=SearchRequestContract)
    provider_receipts: list[SearchProviderReceiptContract] = Field(default_factory=list)
    papers: list[PaperCandidateContract] = Field(default_factory=list)
    verified_papers: list[PaperVerificationContract] = Field(default_factory=list)
    synthesized_findings: list[EvidenceFindingContract] = Field(default_factory=list)
    retrieval_metadata: EvidenceRetrievalMetadataContract = Field(default_factory=EvidenceRetrievalMetadataContract)

    @classmethod
    def from_payload(cls, payload: Any) -> EvidenceBundleContract:
        """Validate a raw evidence bundle payload."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> EvidenceBundleContract:
        """Load and validate one persisted evidence bundle."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


__all__ = [
    "EvidenceBundleContract",
    "EvidenceConfidence",
    "EvidenceFindingContract",
    "EvidenceFindingType",
    "EvidenceRetrievalMetadataContract",
    "LiteratureConsumerName",
    "LiteratureProviderName",
    "LiteratureProviderStatus",
    "LiteratureQueryType",
    "LiteratureSearchFiltersContract",
    "LiteratureSearchStatus",
    "PaperCandidateContract",
    "PaperVerificationContract",
    "PaperVerificationMethod",
    "PaperVerificationStatus",
    "SearchProviderReceiptContract",
    "SearchRequestContract",
]
