"""Pure island selection helpers for the evolutionary search loop."""

from __future__ import annotations

import math
import random
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.agent_contracts import HypothesisContract as Hypothesis
from packages.agent_contracts import IslandStateContract as IslandState


def _as_hypothesis_contract(value: Any) -> Hypothesis:
    """Normalize model-like hypotheses to the shared hypothesis contract."""
    if isinstance(value, Hypothesis):
        return value
    return Hypothesis.from_model_like(value)


class SelectionResult(BaseModel):
    """Result of island selection: strategy plus sampled hypotheses."""

    model_config = ConfigDict(frozen=True)

    strategy: Literal["single_island", "multi_island"] = Field(description="Island selection strategy.")
    hypotheses: list[Hypothesis] = Field(description="Sampled hypotheses to pass to evolution.")

    @field_validator("hypotheses", mode="before")
    @classmethod
    def _normalize_hypotheses(cls, value: Any) -> Any:
        """Accept model-like hypotheses while storing canonical contracts."""
        if not isinstance(value, list):
            return value
        return [_as_hypothesis_contract(item) for item in value]


def select_island_hypotheses(
    islands: dict[str, IslandState],
    hypotheses: dict[str, Hypothesis],
    iteration_count: int,
    *,
    ucb_exploration_constant: float,
    softmax_temperature: float,
    stagnation_epsilon: float,
    rng: Any = random,
) -> SelectionResult:
    """Select island hypotheses for the next evolution step."""
    hypotheses_by_island: dict[str, list[Hypothesis]] = {}
    for hypothesis in hypotheses.values():
        hypotheses_by_island.setdefault(hypothesis.island_id, []).append(hypothesis)

    selectable_islands: dict[str, IslandState] = {}
    viable_hypotheses_by_island: dict[str, list[Hypothesis]] = {}
    for island_id, island_state in islands.items():
        island_hypotheses = hypotheses_by_island.get(island_id, [])
        viable_hypotheses = island_state.get_viable_hypotheses(island_hypotheses)
        if viable_hypotheses:
            selectable_islands[island_id] = island_state
            viable_hypotheses_by_island[island_id] = viable_hypotheses

    if not selectable_islands:
        raise ValueError("Cannot select from islands without any viable hypotheses.")

    all_islands_visited = all(island_state.decayed_visits > 0 for island_state in selectable_islands.values())
    is_stagnating = False
    if all_islands_visited:
        reward_ratios = [
            island_state.decayed_reward / island_state.decayed_visits for island_state in selectable_islands.values()
        ]
        is_stagnating = max(reward_ratios) < stagnation_epsilon

    if is_stagnating and len(selectable_islands) >= 2:
        sorted_selectable_islands = sorted(
            selectable_islands.values(),
            key=lambda state: state.get_best_elo_rating(hypotheses_by_island.get(state.id, [])),
            reverse=True,
        )
        top_island, second_top_island = sorted_selectable_islands[0], sorted_selectable_islands[1]
        return SelectionResult(
            strategy="multi_island",
            hypotheses=[
                sample_hypothesis(
                    viable_hypotheses_by_island[top_island.id],
                    softmax_temperature=softmax_temperature,
                    rng=rng,
                ),
                sample_hypothesis(
                    viable_hypotheses_by_island[second_top_island.id],
                    softmax_temperature=softmax_temperature,
                    rng=rng,
                ),
            ],
        )

    selected_island = select_island_ucb(
        selectable_islands,
        iteration_count,
        ucb_exploration_constant=ucb_exploration_constant,
        rng=rng,
    )
    return SelectionResult(
        strategy="single_island",
        hypotheses=[
            sample_hypothesis(
                viable_hypotheses_by_island[selected_island.id],
                softmax_temperature=softmax_temperature,
                rng=rng,
            )
        ],
    )


def select_island_ucb(
    islands: dict[str, IslandState],
    iteration_count: int,
    *,
    ucb_exploration_constant: float,
    rng: Any = random,
) -> IslandState:
    """Select an island with the UCB1 rule."""
    unvisited_islands = [island for island in islands.values() if island.decayed_visits == 0.0]
    if unvisited_islands:
        return rng.choice(unvisited_islands)

    best_island: IslandState | None = None
    best_island_score = -math.inf
    total_iteration_count = max(iteration_count, 1)

    for island in islands.values():
        exploitation_score = island.decayed_reward / island.decayed_visits
        exploration_score = ucb_exploration_constant * math.sqrt(
            math.log(total_iteration_count) / max(island.visit_count, 1)
        )
        ucb_score = exploitation_score + exploration_score
        if ucb_score > best_island_score:
            best_island_score = ucb_score
            best_island = island

    if best_island is None:
        raise RuntimeError("UCB selection failed: no islands to score")
    return best_island


def sample_hypothesis(
    hypotheses: list[Hypothesis],
    *,
    softmax_temperature: float,
    rng: Any = random,
) -> Hypothesis:
    """Sample one hypothesis from an island using Elo-softmax weighting."""
    if not hypotheses:
        raise ValueError("Cannot sample from island without any available hypotheses.")
    if len(hypotheses) == 1:
        return hypotheses[0]

    max_elo_rating = max(hypothesis.elo_rating for hypothesis in hypotheses)
    weights = [
        10 ** ((hypothesis.elo_rating - max_elo_rating) / (400 * softmax_temperature)) for hypothesis in hypotheses
    ]
    return rng.choices(hypotheses, weights=weights, k=1)[0]


__all__ = ["SelectionResult", "sample_hypothesis", "select_island_hypotheses", "select_island_ucb"]
