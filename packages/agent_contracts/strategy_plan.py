"""Contracts for strategy routing plan artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .policy import GenerationStrategyName


StrategyPhase = Literal[
    "Generation",
    "Reflection",
    "Insights from Reviews",
    "Proximity",
    "Ranking",
    "Evolution",
    "Research Overview",
    "Configuration",
]
StrategyPlanStatus = Literal["planned", "running", "completed", "blocked"]
StrategyAction = Literal[
    "run_configuration",
    "run_generation",
    "run_review",
    "run_insights",
    "run_proximity",
    "run_ranking",
    "continue_evolution",
    "return_to_generation",
    "generate_overview",
    "inspect_state",
]


class StrategyPlanContract(BaseModel):
    """Stable contract for `state/STRATEGY_PLAN.json`."""

    model_config = ConfigDict(extra="ignore")

    status: StrategyPlanStatus = Field(default="planned")
    current_phase: StrategyPhase = Field(default="Generation")
    next_action: StrategyAction = Field(default="run_generation")
    selected_generation_strategies: list[GenerationStrategyName] = Field(default_factory=list)
    selected_evolution_strategies: list[str] = Field(default_factory=list)
    max_new_hypotheses: int = Field(default=0)
    reasoning: list[str] = Field(default_factory=list)
    advisory_recommendation: str = Field(default="")
    signals: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("current_phase", mode="before")
    @classmethod
    def _normalize_current_phase(cls, value: Any) -> Any:
        if value == "ResearchOverview":
            return "Research Overview"
        return value

    @classmethod
    def from_payload(cls, payload: Any) -> StrategyPlanContract:
        """Validate a raw strategy plan payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> StrategyPlanContract:
        """Load and validate a strategy plan artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


class StrategyDecisionRecordContract(StrategyPlanContract):
    """One append-only routing decision record for `STRATEGY_DECISIONS.jsonl`."""

    run_id: str = Field(default="")
    decision_index: int = Field(default=1)
