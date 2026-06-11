"""Host-agent-facing contract mirrors for meta review artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TaskStatus = Literal["pending", "running", "completed", "failed"]


class InsightsFromReviewsContract(BaseModel):
    """Stable insights-from-reviews contract."""

    model_config = ConfigDict(extra="ignore")

    status: TaskStatus = Field(default="pending")
    content: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Any) -> InsightsFromReviewsContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> InsightsFromReviewsContract:
        """Load and validate an insights-from-reviews artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


class ResearchOverviewContract(BaseModel):
    """Stable research overview contract."""

    model_config = ConfigDict(extra="ignore")

    status: TaskStatus = Field(default="pending")
    content: str = Field(default="")

    @classmethod
    def from_payload(cls, payload: Any) -> ResearchOverviewContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> ResearchOverviewContract:
        """Load and validate a research overview artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


class MetaReviewContract(BaseModel):
    """Stable aggregate meta review contract."""

    model_config = ConfigDict(extra="ignore")

    insights_from_reviews: InsightsFromReviewsContract = Field(default_factory=InsightsFromReviewsContract)
    research_overview: ResearchOverviewContract = Field(default_factory=ResearchOverviewContract)

    @classmethod
    def from_payload(cls, payload: Any) -> MetaReviewContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_model_like(cls, value: Any) -> MetaReviewContract:
        """Build the contract from a model-like object or equivalent payload."""
        if hasattr(value, "model_dump"):
            return cls.from_payload(value.model_dump(mode="json"))
        return cls.from_payload(value)

    @classmethod
    def from_json_file(cls, path: Path) -> MetaReviewContract:
        """Load and validate a meta review artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))
