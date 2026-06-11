"""Host-neutral contracts for shared system state, islands, and proximity graphs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .hypothesis import HypothesisContract
from .meta_review import MetaReviewContract
from .ranking import TournamentMatchContract
from .research_plan import ResearchPlanContract


class ProximityEmbeddingMetadataContract(BaseModel):
    """Metadata for one persisted proximity graph embedding."""

    model_config = ConfigDict(extra="ignore")

    provider: str = Field(default="")
    model: str = Field(default="")
    dimensions: int = Field(default=0)
    config_hash: str = Field(default="")
    input_text_hash: str = Field(default="")

    @classmethod
    def from_payload(cls, payload: Any) -> ProximityEmbeddingMetadataContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)


class ProximityGraphContract(BaseModel):
    """Stable contract for hypothesis proximity state."""

    model_config = ConfigDict(extra="ignore")

    similarities: dict[str, dict[str, float]] = Field(default_factory=dict)
    embeddings: dict[str, list[float]] = Field(default_factory=dict)
    embedding_metadata: dict[str, ProximityEmbeddingMetadataContract] = Field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> ProximityGraphContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_model_like(cls, value: Any) -> ProximityGraphContract:
        """Build the contract from a model-like object or equivalent payload."""
        if hasattr(value, "model_dump"):
            return cls.from_payload(value.model_dump(mode="json"))
        return cls.from_payload(value)


class IslandStateContract(BaseModel):
    """Stable contract for UCB island state."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default="")
    decayed_reward: float = Field(default=0.0)
    decayed_visits: float = Field(default=0.0)
    visit_count: int = Field(default=0)

    def get_best_elo_rating(self, island_hypotheses: list[HypothesisContract]) -> float:
        """Return the highest Elo rating among viable island hypotheses."""
        ratings = [hypothesis.elo_rating for hypothesis in island_hypotheses if hypothesis.is_viable]
        return max(ratings) if ratings else 1200.0

    def get_viable_hypotheses(self, island_hypotheses: list[HypothesisContract]) -> list[HypothesisContract]:
        """Return viable hypotheses from the given island slice."""
        return [hypothesis for hypothesis in island_hypotheses if hypothesis.is_viable]

    @classmethod
    def from_payload(cls, payload: Any) -> IslandStateContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_model_like(cls, value: Any) -> IslandStateContract:
        """Build the contract from a model-like object or equivalent payload."""
        if hasattr(value, "model_dump"):
            return cls.from_payload(value.model_dump(mode="json"))
        return cls.from_payload(value)


class CoScientistStateContract(BaseModel):
    """Stable contract for canonical Co-Scientist system state."""

    model_config = ConfigDict(extra="ignore")

    research_plan: ResearchPlanContract = Field(default_factory=ResearchPlanContract)
    hypotheses: dict[str, HypothesisContract] = Field(default_factory=dict)
    tournament_matches: dict[str, TournamentMatchContract] = Field(default_factory=dict)
    islands: dict[str, IslandStateContract] = Field(default_factory=dict)
    proximity_graph: ProximityGraphContract = Field(default_factory=ProximityGraphContract)
    meta_review: MetaReviewContract = Field(default_factory=MetaReviewContract)
    iteration_count: int = Field(default=0)
    convergence_count: int = Field(default=0)

    @classmethod
    def from_payload(cls, payload: Any) -> CoScientistStateContract:
        """Validate a raw payload against the contract."""
        return cls.model_validate(payload)

    @classmethod
    def from_model_like(cls, value: Any) -> CoScientistStateContract:
        """Build the contract from a model-like object or equivalent payload."""
        if hasattr(value, "model_dump"):
            return cls.from_payload(value.model_dump(mode="json"))
        return cls.from_payload(value)

    @classmethod
    def from_json_file(cls, path: Path) -> CoScientistStateContract:
        """Load and validate a serialized system state from disk."""
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))
