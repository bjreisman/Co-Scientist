"""Validated model choices for host-owned scientific tasks."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max", "ultra"]
TaskKind = Literal["configuration", "evidence", "generation", "review", "ranking", "evolution", "meta_review"]


class ModelRoleContract(BaseModel):
    """One custom Codex agent's requested configuration."""

    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    reasoning_effort: ReasoningEffort = "medium"

    @model_validator(mode="after")
    def check_effort(self) -> ModelRoleContract:
        """Reject unsupported no-reasoning settings for known reasoning models."""
        if self.model in {"gpt-6.1-sol", "gpt-6-astra"} and self.reasoning_effort == "none":
            raise ValueError(f"{self.model} does not support reasoning effort 'none'.")
        return self


class ModelPolicyContract(BaseModel):
    """Project policy frozen into a run; deterministic mechanics have no model."""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    enabled: bool = True
    max_concurrent_subagents: int = Field(default=2, ge=1, le=8)
    fallback: Literal["local", "stop"] = "stop"
    roles: dict[str, ModelRoleContract]
    tasks: dict[TaskKind, str]
    skill_overrides: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_roles(self) -> ModelPolicyContract:
        """Require safe agent names and defined roles for every scientific task."""
        for role in self.roles:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", role):
                raise ValueError(f"Invalid role name: {role}")
        expected = {"configuration", "evidence", "generation", "review", "ranking", "evolution", "meta_review"}
        if set(self.tasks) != expected:
            raise ValueError("Define all seven task groups in tasks.")
        missing = (set(self.tasks.values()) | set(self.skill_overrides.values())) - set(self.roles)
        if missing:
            raise ValueError(f"Undefined roles: {sorted(missing)}")
        return self
