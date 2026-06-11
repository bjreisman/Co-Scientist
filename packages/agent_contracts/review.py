"""Host-agent-facing contract mirrors for review artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TaskStatus = Literal["pending", "running", "completed", "failed"]
ObservationConclusion = Literal[
    "already explained",
    "other explanations more likely",
    "missing piece",
    "neutral",
    "disproved",
]


class ArticleContract(BaseModel):
    """Stable article metadata contract."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(default="")
    authors: list[str] = Field(default_factory=list)
    journal: str = Field(default="")
    year: int = Field(default=2026)
    abstract: str = Field(default="")


class RetrievalResultContract(BaseModel):
    """Stable retrieval result contract."""

    model_config = ConfigDict(extra="ignore")

    query: str = Field(default="")
    score: float = Field(default=0.0)
    content: str = Field(default="")
    article: ArticleContract = Field(default_factory=ArticleContract)


class ReviewedAssumptionContract(BaseModel):
    """Stable recursive reviewed assumption contract."""

    model_config = ConfigDict(extra="ignore")

    statement: str = Field(default="")
    sub_assumptions: list[ReviewedAssumptionContract] = Field(default_factory=list)
    correctness: str = Field(default="")


class ObservationContract(BaseModel):
    """Stable observation review item contract."""

    model_config = ConfigDict(extra="ignore")

    reasoning: str = Field(default="")
    conclusion: ObservationConclusion = Field(default="neutral")


class InitialReviewContract(BaseModel):
    """Stable initial review contract."""

    model_config = ConfigDict(extra="ignore")

    status: TaskStatus = Field(default="pending")
    passed: bool = Field(default=False)
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class FullReviewContract(BaseModel):
    """Stable full review contract."""

    model_config = ConfigDict(extra="ignore")

    status: TaskStatus = Field(default="pending")
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    retrieval_results: list[RetrievalResultContract] = Field(default_factory=list)
    evidence_bundle_ids: list[str] = Field(default_factory=list)
    literature_query_ids: list[str] = Field(default_factory=list)


class DeepVerificationReviewContract(BaseModel):
    """Stable deep verification review contract."""

    model_config = ConfigDict(extra="ignore")

    status: TaskStatus = Field(default="pending")
    assumptions: list[ReviewedAssumptionContract] = Field(default_factory=list)


class ObservationReviewContract(BaseModel):
    """Stable observation review contract."""

    model_config = ConfigDict(extra="ignore")

    status: TaskStatus = Field(default="pending")
    observations: list[ObservationContract] = Field(default_factory=list)
    retrieval_results: list[RetrievalResultContract] = Field(default_factory=list)


class SimulationReviewContract(BaseModel):
    """Stable simulation review contract."""

    model_config = ConfigDict(extra="ignore")

    status: TaskStatus = Field(default="pending")
    steps: list[str] = Field(default_factory=list)
    failure_scenarios: list[str] = Field(default_factory=list)


class ReviewSummaryContract(BaseModel):
    """Stable review summary contract."""

    model_config = ConfigDict(extra="ignore")

    status: TaskStatus = Field(default="pending")
    summaries: list[str] = Field(default_factory=list)


class ReviewContract(BaseModel):
    """Stable aggregate review contract."""

    model_config = ConfigDict(extra="ignore")

    initial_review: InitialReviewContract = Field(default_factory=InitialReviewContract)
    full_review: FullReviewContract = Field(default_factory=FullReviewContract)
    deep_verification_review: DeepVerificationReviewContract = Field(default_factory=DeepVerificationReviewContract)
    observation_review: ObservationReviewContract = Field(default_factory=ObservationReviewContract)
    simulation_review: SimulationReviewContract = Field(default_factory=SimulationReviewContract)
    review_summary: ReviewSummaryContract = Field(default_factory=ReviewSummaryContract)

    @classmethod
    def from_payload(cls, payload: Any) -> ReviewContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_model_like(cls, value: Any) -> ReviewContract:
        """Build the contract from a model-like object or equivalent payload."""
        if hasattr(value, "model_dump"):
            return cls.from_payload(value.model_dump(mode="json"))
        return cls.from_payload(value)

    @classmethod
    def from_json_file(cls, path: Path) -> ReviewContract:
        """Load and validate an aggregate review artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


ReviewedAssumptionContract.model_rebuild()
