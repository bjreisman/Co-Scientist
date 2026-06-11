"""Helper functions for top-k selection and ranking opponent choice."""

from __future__ import annotations

from collections.abc import Iterable

from packages.agent_contracts import HypothesisContract as Hypothesis
from packages.agent_contracts import ProximityGraphContract as ProximityGraph


def _iter_hypotheses(hypotheses: dict[str, Hypothesis] | Iterable[Hypothesis]) -> Iterable[Hypothesis]:
    if isinstance(hypotheses, dict):
        return hypotheses.values()
    return hypotheses


def get_top_k_hypotheses(
    hypotheses: dict[str, Hypothesis] | Iterable[Hypothesis],
    k: int,
) -> list[Hypothesis]:
    """Return the viable top-k hypotheses sorted by Elo rating descending."""
    eligible = [hypothesis for hypothesis in _iter_hypotheses(hypotheses) if hypothesis.is_viable]
    return sorted(eligible, key=lambda hypothesis: hypothesis.elo_rating, reverse=True)[: max(k, 0)]


def select_placement_opponents(
    graph: ProximityGraph,
    hypothesis: Hypothesis,
    hypotheses: dict[str, Hypothesis],
    match_count: int,
) -> list[Hypothesis]:
    """Choose placement opponents as the most similar viable hypotheses."""
    similarities = graph.similarities.get(hypothesis.id, {})
    ranked_candidates = sorted(
        (
            (other_id, similarity)
            for other_id, similarity in similarities.items()
            if other_id in hypotheses and other_id != hypothesis.id and hypotheses[other_id].is_viable
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    return [hypotheses[hypothesis_id] for hypothesis_id, _ in ranked_candidates[: max(match_count, 0)]]


def select_fallback_placement_opponents(
    hypothesis: Hypothesis,
    hypotheses: dict[str, Hypothesis] | Iterable[Hypothesis],
    match_count: int,
) -> list[Hypothesis]:
    """Choose deterministic placement opponents when proximity placement is receipt-gated unavailable."""
    ranked_candidates = sorted(
        (
            candidate
            for candidate in _iter_hypotheses(hypotheses)
            if candidate.id != hypothesis.id and candidate.is_viable
        ),
        key=lambda candidate: (-candidate.elo_rating, candidate.id),
    )
    return ranked_candidates[: max(match_count, 0)]


def should_run_ranked_tournament(
    hypothesis: Hypothesis,
    top_k_hypotheses: list[Hypothesis],
    top_k_limit: int,
) -> bool:
    """Return whether the hypothesis should enter the ranked tournament."""
    top_k_ids = {candidate.id for candidate in top_k_hypotheses}
    return hypothesis.id in top_k_ids or len(top_k_hypotheses) < top_k_limit


def select_ranked_opponents(
    hypothesis: Hypothesis,
    hypotheses: dict[str, Hypothesis] | Iterable[Hypothesis],
    top_k_limit: int,
) -> list[Hypothesis]:
    """Return ranked-tournament opponents for the given hypothesis."""
    top_k_hypotheses = get_top_k_hypotheses(hypotheses, top_k_limit)
    if not should_run_ranked_tournament(hypothesis, top_k_hypotheses, top_k_limit):
        return []
    return [candidate for candidate in top_k_hypotheses if candidate.id != hypothesis.id]


__all__ = [
    "get_top_k_hypotheses",
    "select_fallback_placement_opponents",
    "select_placement_opponents",
    "select_ranked_opponents",
    "should_run_ranked_tournament",
]
