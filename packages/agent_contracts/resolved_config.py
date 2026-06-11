"""Contracts for resolved numeric run configuration artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .proximity import EmbeddingProviderConfigContract


ResolvedConfigProfile = Literal["conservative", "balanced", "aggressive"]
ResolvedIterationCapSource = Literal[
    "completion_driven_default",
    "iteration_band",
    "legacy_budget_profile",
    "config_override",
]


class ResolvedGenerationConfigContract(BaseModel):
    """Deterministic generation-time numeric configuration."""

    model_config = ConfigDict(extra="ignore")

    num_debaters: int = Field(default=3)
    max_debate_turns: int = Field(default=5)


class ResolvedIslandConfigContract(BaseModel):
    """Deterministic island-selection numeric configuration."""

    model_config = ConfigDict(extra="ignore")

    ucb_exploration_constant: float = Field(default=1.25)
    decay_factor: float = Field(default=0.9)
    softmax_temperature: float = Field(default=1.0)
    stagnation_epsilon: float = Field(default=0.05)


class ResolvedRankingConfigContract(BaseModel):
    """Deterministic ranking numeric configuration."""

    model_config = ConfigDict(extra="ignore")

    placement_match_count: int = Field(default=10)
    tournament_top_k: int = Field(default=8)
    elo_k_factor: float = Field(default=32.0)


class ResolvedConvergenceConfigContract(BaseModel):
    """Deterministic convergence numeric configuration."""

    model_config = ConfigDict(extra="ignore")

    convergence_count_threshold: int = Field(default=3)
    max_iterations: int = Field(default=0)
    safety_max_iterations: int = Field(default=30)
    iteration_cap_source: ResolvedIterationCapSource = Field(default="completion_driven_default")


class ResolvedProximityConfigContract(EmbeddingProviderConfigContract):
    """Run-frozen proximity embedding provider configuration."""

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def from_payload(cls, payload: Any) -> ResolvedProximityConfigContract:
        """Validate a raw proximity config payload against the contract."""
        return cls.model_validate(payload)


class ResolvedRunConfigContract(BaseModel):
    """Stable contract for `state/RESOLVED_RUN_CONFIG.json`."""

    model_config = ConfigDict(extra="ignore")

    profile: ResolvedConfigProfile = Field(default="balanced")
    generation: ResolvedGenerationConfigContract = Field(default_factory=ResolvedGenerationConfigContract)
    island: ResolvedIslandConfigContract = Field(default_factory=ResolvedIslandConfigContract)
    ranking: ResolvedRankingConfigContract = Field(default_factory=ResolvedRankingConfigContract)
    convergence: ResolvedConvergenceConfigContract = Field(default_factory=ResolvedConvergenceConfigContract)
    proximity: ResolvedProximityConfigContract = Field(default_factory=ResolvedProximityConfigContract)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> ResolvedRunConfigContract:
        """Validate a raw resolved-config payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> ResolvedRunConfigContract:
        """Load and validate a resolved config artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))
