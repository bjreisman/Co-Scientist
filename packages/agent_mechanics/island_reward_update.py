"""Helpers for computing and applying island reward updates."""

from __future__ import annotations

from packages.agent_contracts import HypothesisContract as Hypothesis
from packages.agent_contracts import IslandStateContract as IslandState


def compute_single_island_reward(
    hypotheses: dict[str, Hypothesis],
    selected_island_id: str,
    candidate_hypothesis: Hypothesis,
) -> float:
    """Compute the normalized reward for a single-island evolution result."""
    if not candidate_hypothesis.is_viable:
        return 0.0

    island_elo_ratings = sorted(
        (
            hypothesis.elo_rating
            for hypothesis in hypotheses.values()
            if hypothesis.is_viable and hypothesis.island_id == selected_island_id
        ),
        reverse=True,
    )
    if not island_elo_ratings:
        return 0.0

    best_elo_rating = island_elo_ratings[0]
    second_best_elo_rating = island_elo_ratings[1] if len(island_elo_ratings) >= 2 else best_elo_rating
    global_best_elo_rating = max(hypothesis.elo_rating for hypothesis in hypotheses.values() if hypothesis.is_viable)
    denominator = global_best_elo_rating - second_best_elo_rating
    if denominator > 0:
        return max(0.0, candidate_hypothesis.elo_rating - second_best_elo_rating) / denominator
    if candidate_hypothesis.elo_rating >= global_best_elo_rating:
        return 1.0
    return 0.0


def apply_decayed_island_update(
    islands: dict[str, IslandState],
    selected_island_id: str,
    reward: float,
    decay_factor: float,
) -> None:
    """Apply exponential decay and update reward statistics for the selected island."""
    for island_id, island in islands.items():
        island.decayed_reward *= decay_factor
        island.decayed_visits *= decay_factor
        if island_id == selected_island_id:
            island.decayed_reward += reward
            island.decayed_visits += 1.0
            island.visit_count += 1


def update_single_island_reward(
    islands: dict[str, IslandState],
    hypotheses: dict[str, Hypothesis],
    selected_island_id: str,
    candidate_hypothesis: Hypothesis,
    decay_factor: float,
) -> float:
    """Compute and apply the reward update for a single-island evolution step."""
    reward = compute_single_island_reward(hypotheses, selected_island_id, candidate_hypothesis)
    apply_decayed_island_update(islands, selected_island_id, reward, decay_factor)
    return reward


__all__ = [
    "apply_decayed_island_update",
    "compute_single_island_reward",
    "update_single_island_reward",
]
