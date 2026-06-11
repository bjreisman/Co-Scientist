from __future__ import annotations

from packages.agent_contracts import (
    HypothesisContentContract,
    HypothesisContract,
    InitialReviewContract,
    OriginContract,
    ProximityGraphContract,
    ReviewContract,
)
from packages.agent_mechanics import (
    get_top_k_hypotheses,
    select_fallback_placement_opponents,
    select_placement_opponents,
    select_ranked_opponents,
    should_run_ranked_tournament,
)


def make_hypothesis(hypothesis_id: str, rating: float, *, viable: bool = True) -> HypothesisContract:
    return HypothesisContract(
        id=hypothesis_id,
        elo_rating=rating,
        origin=OriginContract(
            status="completed",
            strategy="literature_exploration_generation",
            content=HypothesisContentContract(
                statement=f"Statement for {hypothesis_id}",
                mechanism="Mechanism",
                experimental_design="Experiment",
                summary=hypothesis_id,
                category="test",
            ),
        ),
        review=ReviewContract(initial_review=InitialReviewContract(status="completed", passed=viable)),
    )


def test_get_top_k_hypotheses_filters_non_viable_entries() -> None:
    hypotheses = {
        "hyp-a": make_hypothesis("hyp-a", 1320.0),
        "hyp-b": make_hypothesis("hyp-b", 1290.0, viable=False),
        "hyp-c": make_hypothesis("hyp-c", 1275.0),
    }

    top_k = get_top_k_hypotheses(hypotheses, 2)

    assert [hypothesis.id for hypothesis in top_k] == ["hyp-a", "hyp-c"]


def test_select_placement_and_ranked_opponents() -> None:
    candidate = make_hypothesis("candidate", 1250.0)
    hypothesis_a = make_hypothesis("hyp-a", 1320.0)
    hypothesis_b = make_hypothesis("hyp-b", 1290.0)
    hypothesis_c = make_hypothesis("hyp-c", 1210.0, viable=False)
    hypotheses = {
        candidate.id: candidate,
        hypothesis_a.id: hypothesis_a,
        hypothesis_b.id: hypothesis_b,
        hypothesis_c.id: hypothesis_c,
    }
    graph = ProximityGraphContract(
        similarities={
            "candidate": {"hyp-a": 0.95, "hyp-b": 0.44, "hyp-c": 0.99},
            "hyp-a": {"candidate": 0.95},
            "hyp-b": {"candidate": 0.44},
            "hyp-c": {"candidate": 0.99},
        }
    )

    placement = select_placement_opponents(graph, candidate, hypotheses, 2)
    ranked = select_ranked_opponents(candidate, hypotheses, 2)

    assert [hypothesis.id for hypothesis in placement] == ["hyp-a", "hyp-b"]
    assert should_run_ranked_tournament(candidate, get_top_k_hypotheses(hypotheses, 2), 2) is False
    assert ranked == []

    candidate.elo_rating = 1400.0
    ranked = select_ranked_opponents(candidate, hypotheses, 2)
    assert [hypothesis.id for hypothesis in ranked] == ["hyp-a"]


def test_select_fallback_placement_opponents_uses_viable_elo_frontier() -> None:
    candidate = make_hypothesis("candidate", 1250.0)
    hypothesis_a = make_hypothesis("hyp-a", 1290.0)
    hypothesis_b = make_hypothesis("hyp-b", 1320.0)
    hypothesis_c = make_hypothesis("hyp-c", 1400.0, viable=False)
    hypotheses = {
        candidate.id: candidate,
        hypothesis_a.id: hypothesis_a,
        hypothesis_b.id: hypothesis_b,
        hypothesis_c.id: hypothesis_c,
    }

    placement = select_fallback_placement_opponents(candidate, hypotheses, 2)

    assert [hypothesis.id for hypothesis in placement] == ["hyp-b", "hyp-a"]
