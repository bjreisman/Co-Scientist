"""Contracts for run-local pipeline summary and current-stage artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PipelineMode = Literal["host-agent"]
PipelineStatus = Literal["not_started", "running", "completed", "failed"]
_PIPELINE_STAGE_VALUES = frozenset(
    {
        "Bootstrap",
        "Idle",
        "Configuration",
        "Generation",
        "Evolution",
        "Reflection",
        "Insights from Reviews",
        "Proximity",
        "Ranking",
        "Research Overview",
        "Completed",
        "Failed",
    }
)
_PIPELINE_STAGE_ALIASES = {"ResearchOverview": "Research Overview"}
_PIPELINE_SKILL_VALUES = frozenset(
    {
        "research-config",
        "hypothesis-generation-pipeline",
        "hypothesis-evolution-loop",
        "hypothesis-review-pipeline",
        "insights-from-reviews",
        "hypothesis-proximity-update",
        "hypothesis-ranking-pipeline",
        "research-overview-pipeline",
    }
)


def _normalize_stage(value: str) -> str:
    if value in _PIPELINE_STAGE_VALUES:
        return value
    return _PIPELINE_STAGE_ALIASES.get(value, "")


def _normalize_stage_trail(value: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in value:
        stage = _normalize_stage(item)
        if stage and stage not in normalized:
            normalized.append(stage)
    return normalized


class CurrentStageContract(BaseModel):
    """Stable contract for `state/CURRENT_STAGE.json`."""

    model_config = ConfigDict(extra="ignore")

    runId: str = Field(default="")
    stage: str = Field(default="")
    stageTrail: list[str] = Field(default_factory=list)
    updatedAt: str = Field(default="")

    @field_validator("stage")
    @classmethod
    def _validate_stage(cls, value: str) -> str:
        if not value or not _normalize_stage(value):
            raise ValueError("CURRENT_STAGE.json has an invalid `stage` field.")
        return value

    @field_validator("stageTrail")
    @classmethod
    def _validate_stage_trail(cls, value: list[str]) -> list[str]:
        normalized = _normalize_stage_trail(value)
        if normalized != value:
            raise ValueError("CURRENT_STAGE.json has an invalid `stageTrail` field.")
        return value

    @classmethod
    def from_payload(cls, payload: Any) -> CurrentStageContract:
        """Validate a raw current-stage payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> CurrentStageContract:
        """Load and validate a current-stage artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


class PipelineStateContract(BaseModel):
    """Stable contract for `state/PIPELINE_STATE.json`."""

    model_config = ConfigDict(extra="ignore")

    runId: str = Field(default="")
    updatedAt: str = Field(default="")
    iterationCount: int = Field(default=0)
    convergenceCount: int = Field(default=0)
    researchGoal: str = Field(default="")
    hypothesisCount: int = Field(default=0)
    viableHypothesisCount: int = Field(default=0)
    tournamentMatchCount: int = Field(default=0)
    islandCount: int = Field(default=0)
    topHypothesisIds: list[str] = Field(default_factory=list)
    mode: PipelineMode = Field(default="host-agent")
    status: PipelineStatus = Field(default="not_started")
    currentPhase: str = Field(default="")
    currentSkill: str = Field(default="")
    currentIteration: int = Field(default=0)
    completedSkills: list[str] = Field(default_factory=list)
    lastFailedSkill: str | None = Field(default=None)
    resumeInputs: dict[str, Any] = Field(default_factory=dict)
    stageTrail: list[str] = Field(default_factory=list)

    @field_validator("currentPhase")
    @classmethod
    def _validate_current_phase(cls, value: str) -> str:
        if value and not _normalize_stage(value):
            raise ValueError("PIPELINE_STATE.json has an invalid `currentPhase` field.")
        return value

    @field_validator("currentSkill")
    @classmethod
    def _validate_current_skill(cls, value: str) -> str:
        if value and value not in _PIPELINE_SKILL_VALUES:
            raise ValueError("PIPELINE_STATE.json has an invalid `currentSkill` field.")
        return value

    @field_validator("completedSkills")
    @classmethod
    def _validate_completed_skills(cls, value: list[str]) -> list[str]:
        unknown = [skill for skill in value if skill not in _PIPELINE_SKILL_VALUES]
        if unknown:
            raise ValueError("PIPELINE_STATE.json contains unknown entries in `completedSkills`.")
        return value

    @field_validator("lastFailedSkill")
    @classmethod
    def _validate_last_failed_skill(cls, value: str | None) -> str | None:
        if value is not None and value not in _PIPELINE_SKILL_VALUES:
            raise ValueError("PIPELINE_STATE.json has an invalid `lastFailedSkill` field.")
        return value

    @field_validator("stageTrail")
    @classmethod
    def _validate_stage_trail(cls, value: list[str]) -> list[str]:
        normalized = _normalize_stage_trail(value)
        if normalized != value:
            raise ValueError("PIPELINE_STATE.json has an invalid `stageTrail` field.")
        return value

    @classmethod
    def from_payload(cls, payload: Any) -> PipelineStateContract:
        """Validate a raw pipeline-state payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> PipelineStateContract:
        """Load and validate a pipeline-state artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))
