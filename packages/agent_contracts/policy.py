"""Contracts for run policy and policy decision artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


GenerationStrategyName = Literal[
    "literature_exploration_generation",
    "scientific_debates_generation",
    "assumptions_identification_generation",
]
ReviewModeName = Literal[
    "full_review",
    "deep_verification_review",
    "observation_review",
    "simulation_review",
]
ExplorationMode = Literal["conservative", "balanced", "aggressive"]
GenerationBias = Literal["literature_heavy", "debate_heavy", "assumptions_heavy", "mixed"]
ReviewRigor = Literal["light", "standard", "strict"]
EvolutionStyle = Literal["exploit", "balanced", "diversify"]
BudgetProfile = Literal["low", "medium", "high"]
StopPolicy = Literal["exploratory", "standard", "strict"]
IterationPolicy = Literal["completion_driven", "capped"]
IterationBand = Literal["6_10", "10_14", "15_20", "20_30"]
HumanCheckpoint = Literal["auto", "before_overview", "before_completion", "every_major_stage"]
PolicyDecisionStatus = Literal["draft", "completed", "overridden"]

_CANONICAL_REVIEW_MODES: tuple[ReviewModeName, ...] = (
    "full_review",
    "deep_verification_review",
    "observation_review",
    "simulation_review",
)


class RunPolicySettingsContract(BaseModel):
    """Structured high-level routing policy for one run."""

    model_config = ConfigDict(extra="ignore")

    exploration_mode: ExplorationMode = Field(default="balanced")
    generation_bias: GenerationBias = Field(default="mixed")
    review_rigor: ReviewRigor = Field(default="standard")
    evolution_style: EvolutionStyle = Field(default="balanced")
    budget_profile: BudgetProfile = Field(default="medium")
    stop_policy: StopPolicy = Field(default="standard")
    iteration_policy: IterationPolicy = Field(default="completion_driven")
    iteration_band: IterationBand | None = Field(default=None)
    allowed_generation_strategies: list[GenerationStrategyName] = Field(default_factory=list)
    allowed_review_modes: list[ReviewModeName] = Field(default_factory=lambda: list(_CANONICAL_REVIEW_MODES))
    human_checkpoint: HumanCheckpoint = Field(default="auto")

    @field_validator("allowed_review_modes", mode="before")
    @classmethod
    def _normalize_allowed_review_modes(cls, value: Any) -> list[ReviewModeName]:
        # Review-stage coverage is fixed: every run must keep the full canonical review stack enabled.
        return list(_CANONICAL_REVIEW_MODES)

    @classmethod
    def from_payload(cls, payload: Any) -> RunPolicySettingsContract:
        """Validate a raw policy payload against the contract."""
        return cls.model_validate(payload)


class RunPolicyContract(BaseModel):
    """Stable contract for `RUN_POLICY.yaml`."""

    model_config = ConfigDict(extra="ignore")

    input_file: str = Field(default="")
    log_file: str = Field(default="co_scientist.log")
    policy: RunPolicySettingsContract = Field(default_factory=RunPolicySettingsContract)

    @classmethod
    def from_payload(cls, payload: Any) -> RunPolicyContract:
        """Validate a raw policy payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> RunPolicyContract:
        """Load and validate a JSON-serialized run policy artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def from_yaml_file(cls, path: Path) -> RunPolicyContract:
        """Load and validate a YAML-serialized run policy artifact from disk."""
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in run policy artifact: {path}") from exc
        return cls.from_payload(payload)

    def to_yaml_text(self) -> str:
        """Render the run policy as a stable YAML document."""
        return yaml.safe_dump(self.model_dump(mode="json"), allow_unicode=True, sort_keys=False)


class PolicyDecisionContract(BaseModel):
    """Stable contract for `state/POLICY_DECISION.json`."""

    model_config = ConfigDict(extra="ignore")

    status: PolicyDecisionStatus = Field(default="completed")
    run_id: str = Field(default="")
    policy: RunPolicySettingsContract = Field(default_factory=RunPolicySettingsContract)
    rationale: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> PolicyDecisionContract:
        """Validate a raw policy decision payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> PolicyDecisionContract:
        """Load and validate a policy decision artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))
