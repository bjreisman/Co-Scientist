from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)


from packages.agent_contracts import (
    CoScientistStateContract,
    DeepVerificationReviewContract,
    FullReviewContract,
    HypothesisContentContract,
    HypothesisContract,
    InitialReviewContract,
    InsightsFromReviewsContract,
    IslandStateContract,
    MetaReviewContract,
    ObservationContract,
    ObservationReviewContract,
    OriginContract,
    ProximityGraphContract,
    ResearchOverviewContract,
    ResearchPlanContract,
    ReviewContract,
    ReviewedAssumptionContract,
    ReviewSummaryContract,
    SimulationReviewContract,
    TournamentMatchContract,
)


def _build_review(*, passed: bool, summary: str) -> ReviewContract:
    return ReviewContract(
        initial_review=InitialReviewContract(
            status="completed",
            passed=passed,
            preferences=["Mechanistically plausible"],
            constraints=["Experimentally testable"],
        ),
        full_review=FullReviewContract(
            status="completed",
            preferences=["Grounded in prior work"],
            constraints=["Needs direct validation"],
        ),
        deep_verification_review=DeepVerificationReviewContract(
            status="completed",
            assumptions=[ReviewedAssumptionContract(statement="Core assumption", correctness="supported")],
        ),
        observation_review=ObservationReviewContract(
            status="completed",
            observations=[
                ObservationContract(
                    reasoning="Observed trend is directionally consistent with the hypothesis.",
                    conclusion="missing piece",
                )
            ],
        ),
        simulation_review=SimulationReviewContract(
            status="completed",
            steps=["Run perturbation", "Measure response"],
            failure_scenarios=["Compensation through a parallel pathway"],
        ),
        review_summary=ReviewSummaryContract(status="completed", summaries=[summary]),
    )


def build_hypothesis(
    hypothesis_id: str,
    rating: float,
    island_id: str,
    *,
    passed: bool = True,
    parent_ids: list[str] | None = None,
    summary: str | None = None,
    category: str = "test",
    strategy: str = "assumptions_identification_generation",
) -> HypothesisContract:
    label = summary or hypothesis_id
    return HypothesisContract(
        id=hypothesis_id,
        elo_rating=rating,
        island_id=island_id,
        parent_ids=parent_ids or [],
        origin=OriginContract(
            status="completed",
            strategy=strategy,
            content=HypothesisContentContract(
                statement=f"Statement for {hypothesis_id}",
                mechanism=f"Mechanism for {hypothesis_id}",
                experimental_design=f"Experiment for {hypothesis_id}",
                summary=label,
                category=category,
            ),
        ),
        review=_build_review(passed=passed, summary=f"Summary for {label}"),
    )


@pytest.fixture
def sample_state() -> CoScientistStateContract:
    hypothesis_one = build_hypothesis(
        "hyp-001",
        1320.0,
        "island-a",
        summary="Feedback-driven response amplification",
        category="signal-adaptation",
    )
    hypothesis_two = build_hypothesis(
        "hyp-002",
        1245.0,
        "island-b",
        parent_ids=["hyp-001"],
        summary="Chromatin-state response shift",
        category="epigenetic-adaptation",
    )
    return CoScientistStateContract(
        research_plan=ResearchPlanContract(
            status="completed",
            research_goal="Find an interpretable drug response mechanism.",
            preferences=["Novel mechanism", "Biologically grounded"],
            constraints=["Must be testable in vitro", "Avoid known toxic pathways"],
        ),
        hypotheses={
            hypothesis_one.id: hypothesis_one,
            hypothesis_two.id: hypothesis_two,
        },
        tournament_matches={
            "match-001": TournamentMatchContract(
                id="match-001",
                status="completed",
                hypothesis_1_id="hyp-001",
                hypothesis_2_id="hyp-002",
                match_strategy="placement_tournament",
                reasoning="Hypothesis one is better grounded and easier to test.",
                winner_id="hyp-001",
            )
        },
        islands={
            "island-a": IslandStateContract(id="island-a", decayed_reward=0.8, decayed_visits=1.2, visit_count=2),
            "island-b": IslandStateContract(id="island-b", decayed_reward=0.4, decayed_visits=0.7, visit_count=1),
        },
        proximity_graph=ProximityGraphContract(
            similarities={
                "hyp-001": {"hyp-002": 0.41},
                "hyp-002": {"hyp-001": 0.41},
            },
            embeddings={
                "hyp-001": [0.1, 0.2, 0.3],
                "hyp-002": [0.2, 0.1, 0.4],
            },
        ),
        meta_review=MetaReviewContract(
            insights_from_reviews=InsightsFromReviewsContract(
                status="completed",
                content=["Mechanistic grounding consistently improves ranking performance."],
            ),
            research_overview=ResearchOverviewContract(
                status="completed",
                content="The current frontier favors mechanistic hypotheses with direct validation loops.",
            ),
        ),
        iteration_count=2,
        convergence_count=1,
    )
