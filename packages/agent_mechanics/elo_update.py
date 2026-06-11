"""Pure Elo update helpers for tournament match results."""

from __future__ import annotations

from packages.agent_contracts import HypothesisContract as Hypothesis
from packages.agent_contracts import HypothesisMatchupContract as HypothesisMatchup
from packages.agent_contracts import TournamentMatchContract as TournamentMatch


def compute_elo_delta(winner_rating: float, loser_rating: float, k_factor: float = 32.0) -> float:
    """Compute the Elo rating change for a single decisive match."""
    expected_winner = 1.0 / (1.0 + 10.0 ** ((loser_rating - winner_rating) / 400.0))
    return k_factor * (1.0 - expected_winner)


def apply_elo_updates(
    matches: list[TournamentMatch],
    matchups: list[HypothesisMatchup],
    strategy: str,
    *,
    k_factor: float = 32.0,
) -> dict[str, float]:
    """Apply batch Elo updates and match references to the involved hypotheses.

    The function mirrors the existing ranking behavior:

    - match ordering within one batch does not affect final ratings
    - the challenger hypothesis records placement or ranked match IDs
    - the defending hypothesis records ranked match IDs for both strategies
    """
    if strategy not in {"placement_tournament", "ranked_tournament"}:
        raise ValueError(f"Unknown tournament strategy: {strategy}")

    all_hypotheses: dict[str, Hypothesis] = {}
    for matchup in matchups:
        all_hypotheses[matchup.hypothesis_1.id] = matchup.hypothesis_1
        all_hypotheses[matchup.hypothesis_2.id] = matchup.hypothesis_2

    deltas: dict[str, float] = dict.fromkeys(all_hypotheses, 0.0)
    is_placement = strategy == "placement_tournament"

    for match_result, matchup in zip(matches, matchups, strict=True):
        hypothesis_1 = matchup.hypothesis_1
        hypothesis_2 = matchup.hypothesis_2

        if _match_already_applied(match_result.id, hypothesis_1, hypothesis_2, is_placement=is_placement):
            continue

        if is_placement:
            _append_unique(hypothesis_1.placement_match_ids, match_result.id)
        else:
            _append_unique(hypothesis_1.ranked_match_ids, match_result.id)
        _append_unique(hypothesis_2.ranked_match_ids, match_result.id)

        winner_id = match_result.winner_id
        valid_ids = {hypothesis_1.id, hypothesis_2.id}
        if winner_id not in valid_ids:
            continue

        if winner_id == hypothesis_1.id:
            delta = compute_elo_delta(hypothesis_1.elo_rating, hypothesis_2.elo_rating, k_factor)
            deltas[hypothesis_1.id] += delta
            deltas[hypothesis_2.id] -= delta
        else:
            delta = compute_elo_delta(hypothesis_2.elo_rating, hypothesis_1.elo_rating, k_factor)
            deltas[hypothesis_2.id] += delta
            deltas[hypothesis_1.id] -= delta

    for hypothesis_id, hypothesis in all_hypotheses.items():
        hypothesis.elo_rating += deltas[hypothesis_id]

    return deltas


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _match_already_applied(
    match_id: str,
    hypothesis_1: Hypothesis,
    hypothesis_2: Hypothesis,
    *,
    is_placement: bool,
) -> bool:
    if is_placement:
        return match_id in hypothesis_1.placement_match_ids and match_id in hypothesis_2.ranked_match_ids
    return match_id in hypothesis_1.ranked_match_ids and match_id in hypothesis_2.ranked_match_ids


__all__ = ["apply_elo_updates", "compute_elo_delta"]
