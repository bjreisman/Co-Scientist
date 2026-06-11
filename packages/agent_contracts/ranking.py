"""Host-neutral contracts for tournament ranking artifacts and pairings."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .hypothesis import HypothesisContract


TaskStatus = Literal["pending", "running", "completed", "failed"]
RankingUpdateStatus = Literal["completed"]
TournamentStrategy = Literal["placement_tournament", "ranked_tournament"]


class TournamentMatchContentContract(BaseModel):
    """Stable tournament match content contract."""

    model_config = ConfigDict(extra="ignore")

    reasoning: str = Field(default="")
    winner_id: str = Field(default="")


class TournamentMatchContract(TournamentMatchContentContract):
    """Stable tournament match artifact contract."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default="")
    status: TaskStatus = Field(default="pending")
    hypothesis_1_id: str = Field(default="")
    hypothesis_2_id: str = Field(default="")
    match_strategy: TournamentStrategy = Field(default="placement_tournament")
    debate_turns: list[dict[str, str]] = Field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: Any) -> TournamentMatchContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_model_like(cls, value: Any) -> TournamentMatchContract:
        """Build the contract from a model-like object or equivalent payload."""
        if hasattr(value, "model_dump"):
            return cls.from_payload(value.model_dump(mode="json"))
        return cls.from_payload(value)

    @classmethod
    def from_json_file(cls, path: Path) -> TournamentMatchContract:
        """Load and validate a tournament match artifact from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


class HypothesisMatchupContract(BaseModel):
    """Stable contract for one hypothesis matchup."""

    model_config = ConfigDict(extra="ignore")

    hypothesis_1: HypothesisContract = Field(default_factory=HypothesisContract)
    hypothesis_2: HypothesisContract = Field(default_factory=HypothesisContract)
    match: TournamentMatchContract | None = Field(default=None)

    @classmethod
    def from_payload(cls, payload: Any) -> HypothesisMatchupContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_model_like(cls, value: Any) -> HypothesisMatchupContract:
        """Build the contract from a model-like object or equivalent payload."""
        if hasattr(value, "model_dump"):
            return cls.from_payload(value.model_dump(mode="json"))
        return cls.from_payload(value)


class RankingUpdateReceiptContract(BaseModel):
    """Run-local receipt for one canonical Elo writeback batch."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default="")
    status: RankingUpdateStatus = Field(default="completed")
    strategy: TournamentStrategy = Field(default="placement_tournament")
    match_ids: list[str] = Field(default_factory=list)
    touched_hypothesis_ids: list[str] = Field(default_factory=list)
    elo_before: dict[str, float] = Field(default_factory=dict)
    elo_after: dict[str, float] = Field(default_factory=dict)
    updated_hypothesis_paths: list[str] = Field(default_factory=list)
    receipt_path: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> RankingUpdateReceiptContract:
        """Validate a raw ranking update receipt payload."""
        return cls.model_validate(payload)

    @classmethod
    def from_json_file(cls, path: Path) -> RankingUpdateReceiptContract:
        """Load and validate one ranking update receipt artifact."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))
