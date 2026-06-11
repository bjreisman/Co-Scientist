"""Host-agent-facing contract mirrors for hypothesis artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .review import RetrievalResultContract, ReviewContract


TaskStatus = Literal["pending", "running", "completed", "failed"]


class GeneratedAssumptionContract(BaseModel):
    """Stable recursive generated assumption contract."""

    model_config = ConfigDict(extra="ignore")

    statement: str = Field(default="")
    sub_assumptions: list[GeneratedAssumptionContract] = Field(default_factory=list)


class HypothesisContentContract(BaseModel):
    """Stable hypothesis content contract."""

    model_config = ConfigDict(extra="ignore")

    statement: str = Field(default="")
    mechanism: str = Field(default="")
    experimental_design: str = Field(default="")
    summary: str = Field(default="")
    category: str = Field(default="")


class OriginContract(BaseModel):
    """Stable origin contract across generation and evolution strategies."""

    model_config = ConfigDict(extra="allow")

    status: TaskStatus = Field(default="pending")
    strategy: str = Field(default="")
    content: HypothesisContentContract = Field(default_factory=HypothesisContentContract)
    retrieval_results: list[RetrievalResultContract] = Field(default_factory=list)
    evidence_bundle_ids: list[str] = Field(default_factory=list)
    literature_query_ids: list[str] = Field(default_factory=list)
    debate_turns: list[dict[str, str]] = Field(default_factory=list)
    assumptions: list[GeneratedAssumptionContract] = Field(default_factory=list)


class HypothesisContract(BaseModel):
    """Stable contract for `hypotheses/<id>/HYPOTHESIS.json`."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default="")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    elo_rating: float = Field(default=1200.0)
    origin: OriginContract = Field(default_factory=OriginContract)
    review: ReviewContract = Field(default_factory=ReviewContract)
    island_id: str = Field(default="")
    parent_ids: list[str] = Field(default_factory=list)
    placement_match_ids: list[str] = Field(default_factory=list)
    ranked_match_ids: list[str] = Field(default_factory=list)

    @property
    def is_viable(self) -> bool:
        """Whether the hypothesis passed the initial review gate."""
        return self.review.initial_review.passed

    @classmethod
    def from_payload(cls, payload: Any) -> HypothesisContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_model_like(cls, value: Any) -> HypothesisContract:
        """Build the contract from a model-like object or equivalent payload."""
        if hasattr(value, "model_dump"):
            return cls.from_payload(value.model_dump(mode="json"))
        return cls.from_payload(value)

    @classmethod
    def from_json_file(cls, path: Path) -> HypothesisContract:
        """Load and validate a hypothesis artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


GeneratedAssumptionContract.model_rebuild()
