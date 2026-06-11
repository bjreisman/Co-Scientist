"""Host-agent-facing contract mirror for research plan artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TaskStatus = Literal["pending", "running", "completed", "failed"]


class ResearchPlanContract(BaseModel):
    """Stable contract for `research_plan/RESEARCH_PLAN.json`."""

    model_config = ConfigDict(extra="ignore")

    status: TaskStatus = Field(default="pending")
    research_goal: str = Field(default="")
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Any) -> ResearchPlanContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_model_like(cls, value: Any) -> ResearchPlanContract:
        """Build the contract from a model-like object or equivalent payload."""
        if hasattr(value, "model_dump"):
            return cls.from_payload(value.model_dump(mode="json"))
        return cls.from_payload(value)

    @classmethod
    def from_json_file(cls, path: Path) -> ResearchPlanContract:
        """Load and validate a research plan artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))
