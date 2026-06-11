"""Host-agent-facing contract mirrors for evolution and completion control artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


EvolutionLoopStatus = Literal["not_started", "running", "completed", "blocked"]
CompletionReadiness = Literal["continue_evolution", "ready_for_overview", "ready_for_completion", "blocked"]
CompletionAction = Literal["continue_evolution", "generate_overview", "complete", "inspect_state"]
EvolutionStopReason = Literal[
    "",
    "convergence_reached",
    "max_iterations_reached",
    "safety_iteration_limit_reached",
    "candidate_quality_plateau",
    "no_viable_candidates",
    "operator_stop",
    "validation_blocked",
    "budget_exhausted",
    "manual_override_complete",
]


class EvolutionStateContract(BaseModel):
    """Stable contract for `state/EVOLUTION_STATE.json`."""

    model_config = ConfigDict(extra="ignore")

    status: EvolutionLoopStatus = Field(default="not_started")
    iterationCount: int = Field(default=0)
    convergenceCount: int = Field(default=0)
    convergenceThreshold: int = Field(default=0)
    maxIterations: int = Field(default=0)
    safetyMaxIterations: int = Field(default=0)
    effectiveTopK: int = Field(default=0)
    lastSelectedIsland: str = Field(default="")
    lastSelectedStrategy: str = Field(default="")
    enteredTopKLastRound: bool | None = Field(default=None)
    stopPolicy: str = Field(default="")
    iterationPolicy: str = Field(default="")
    iterationBand: str = Field(default="")
    safetyLimitHit: bool = Field(default=False)
    stopReason: EvolutionStopReason = Field(default="")
    overviewEligible: bool = Field(default=False)
    topHypothesisIds: list[str] = Field(default_factory=list)
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> EvolutionStateContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> EvolutionStateContract:
        """Load and validate an evolution state artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


class CompletionDecisionContract(BaseModel):
    """Stable contract for `state/COMPLETION_DECISION.json`."""

    model_config = ConfigDict(extra="ignore")

    decision: CompletionAction = Field(default="continue_evolution")
    verifierRecommendation: CompletionAction = Field(default="continue_evolution")
    override: bool = Field(default=False)
    rationale: list[str] = Field(default_factory=list)
    requestedSkill: str = Field(default="co-scientist-pipeline")
    decidedAt: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> CompletionDecisionContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> CompletionDecisionContract:
        """Load and validate a completion decision artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))
