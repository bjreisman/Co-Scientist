"""Contracts for append-only evolution round replay records."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


EvolutionRoundStatus = Literal["completed"]
EvolutionSelectionStrategy = Literal["single_island", "multi_island"]


class EvolutionRoundRecordContract(BaseModel):
    """One completed evolution round receipt for `state/EVOLUTION_ROUNDS.jsonl`."""

    model_config = ConfigDict(extra="ignore")

    run_id: str = Field(min_length=1)
    round_index: int = Field(ge=1)
    decision_index: int = Field(ge=1)
    status: EvolutionRoundStatus = Field(default="completed")
    selection_strategy: EvolutionSelectionStrategy
    selected_island_ids: list[str] = Field(min_length=1)
    parent_hypothesis_ids: list[str] = Field(min_length=1)
    chosen_evolution_strategy: str = Field(min_length=1)
    child_hypothesis_id: str = Field(min_length=1)
    child_island_id: str = Field(default="")
    review_passed: bool | None = Field(default=None)
    proximity_receipt_status: str = Field(default="")
    placement_match_ids: list[str] = Field(default_factory=list)
    ranked_match_ids: list[str] = Field(default_factory=list)
    previous_top_k_ids: list[str] = Field(default_factory=list)
    current_top_k_ids: list[str] = Field(default_factory=list)
    entered_top_k: bool
    convergence_count_before: int = Field(ge=0)
    convergence_count_after: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_payload(cls, payload: Any) -> EvolutionRoundRecordContract:
        """Validate a raw evolution round payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_jsonl_file(cls, path: Path) -> list[EvolutionRoundRecordContract]:
        """Load and validate append-only evolution round records from disk."""
        if not path.exists():
            return []
        return [
            cls.from_payload(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


__all__ = [
    "EvolutionRoundRecordContract",
    "EvolutionRoundStatus",
    "EvolutionSelectionStrategy",
]
