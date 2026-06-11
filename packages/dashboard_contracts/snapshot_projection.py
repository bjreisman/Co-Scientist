"""Pure dashboard snapshot builders shared by API and artifact export."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from packages.agent_contracts import (
    CoScientistStateContract,
    HypothesisContract,
    ObservationContract,
    ReviewContract,
    ReviewedAssumptionContract,
)
from packages.dashboard_contracts.dashboard import (
    DashboardHypothesis,
    DashboardHypothesisContent,
    DashboardIslandState,
    DashboardOrigin,
    DashboardResearchPlan,
    DashboardReviewBundle,
    DashboardReviewEntry,
    DashboardReviewGate,
    DashboardReviewSection,
    DashboardSnapshot,
    DashboardState,
    GraphSeed,
    GraphSeedEdge,
    GraphSeedIsland,
    GraphSeedIslandMetrics,
    GraphSeedNode,
    InsightSection,
    MetricItem,
    RankingItem,
)


_RANKING_TONES = ("blue", "violet", "cyan")

__all__ = ["build_dashboard_snapshot", "build_empty_dashboard_snapshot"]


def build_empty_dashboard_snapshot(run_id: str, updated_at: str) -> DashboardSnapshot:
    """Build an empty snapshot for runs without persisted state."""
    return DashboardSnapshot(
        runId=run_id,
        updatedAt=updated_at,
        hasData=False,
        state=DashboardState(),
        metrics=[
            MetricItem(label="Hypotheses", value=0, tone="blue"),
            MetricItem(label="Islands", value=0, tone="green"),
            MetricItem(label="Iterations", value=0, tone="amber"),
            MetricItem(label="Convergence", value=0, tone="violet"),
        ],
        ranking=[],
        graphSeed=GraphSeed(),
        insightSections=[
            InsightSection(
                title="Insights From Reviews",
                badge="Synthesized",
                icon="message-square",
                items=["No review insights available yet."],
            ),
            InsightSection(
                title="Research Overview",
                badge="In Review",
                icon="book-open",
                items=["No research overview available yet."],
            ),
            InsightSection(
                title="Iteration Strategy",
                badge="Pending",
                icon="brain",
                items=["No iteration strategy summary available yet."],
            ),
        ],
    )


def build_dashboard_snapshot(run_id: str, updated_at: str, state: CoScientistStateContract | Any) -> DashboardSnapshot:
    """Build a full dashboard snapshot from the canonical state."""
    if not isinstance(state, CoScientistStateContract):
        state = CoScientistStateContract.from_model_like(state)
    hypothesis_aliases = _build_hypothesis_aliases(state)
    island_aliases = _build_island_aliases(state)
    return DashboardSnapshot(
        runId=run_id,
        updatedAt=updated_at,
        hasData=True,
        state=_build_state(state, hypothesis_aliases, island_aliases),
        metrics=_build_metrics(state),
        ranking=_build_ranking(state, hypothesis_aliases),
        graphSeed=_build_graph_seed(state, hypothesis_aliases, island_aliases),
        insightSections=_build_insight_sections(state),
    )


def _build_state(
    state: CoScientistStateContract,
    hypothesis_aliases: dict[str, str],
    island_aliases: dict[str, str],
) -> DashboardState:
    hypotheses = {
        hypothesis.id: _build_hypothesis(hypothesis, hypothesis_aliases, island_aliases)
        for hypothesis in sorted(state.hypotheses.values(), key=lambda item: item.elo_rating, reverse=True)
    }
    islands = {
        island.id: DashboardIslandState(
            id=island.id,
            alias=island_aliases.get(island.id, island.id[:8]),
            decayed_reward=round(island.decayed_reward, 3),
            decayed_visits=round(island.decayed_visits, 3),
            visit_count=island.visit_count,
        )
        for island in state.islands.values()
    }
    return DashboardState(
        research_plan=DashboardResearchPlan(
            research_goal=state.research_plan.research_goal,
            preferences=state.research_plan.preferences,
            constraints=state.research_plan.constraints,
        ),
        hypotheses=hypotheses,
        islands=islands,
        iteration_count=state.iteration_count,
        convergence_count=state.convergence_count,
    )


def _build_hypothesis(
    hypothesis: HypothesisContract,
    hypothesis_aliases: dict[str, str],
    island_aliases: dict[str, str],
) -> DashboardHypothesis:
    content = hypothesis.origin.content
    return DashboardHypothesis(
        id=hypothesis.id,
        alias=hypothesis_aliases.get(hypothesis.id, hypothesis.id[:8]),
        timestamp=hypothesis.timestamp.isoformat(),
        elo_rating=round(hypothesis.elo_rating),
        origin=DashboardOrigin(
            strategy=hypothesis.origin.strategy,
            content=DashboardHypothesisContent(
                statement=content.statement,
                mechanism=content.mechanism,
                experimental_design=content.experimental_design,
                summary=content.summary,
                category=content.category,
            ),
        ),
        review=DashboardReviewBundle(
            initial_review=DashboardReviewGate(
                passed=hypothesis.review.initial_review.passed
                if hypothesis.review.initial_review.status == "completed"
                else None,
                summary=_build_initial_review_summary(hypothesis),
            ),
            full_review=DashboardReviewGate(summary=_build_full_review_summary(hypothesis)),
            deep_verification_review=DashboardReviewGate(
                summary=_build_deep_verification_summary(
                    hypothesis.review.deep_verification_review.assumptions
                    if hypothesis.review.deep_verification_review.status == "completed"
                    else []
                )
            ),
            observation_review=DashboardReviewGate(
                summary=_build_observation_summary(
                    hypothesis.review.observation_review.observations
                    if hypothesis.review.observation_review.status == "completed"
                    else []
                )
            ),
            simulation_review=DashboardReviewGate(
                summary=_build_simulation_summary(
                    hypothesis.review.simulation_review.failure_scenarios
                    if hypothesis.review.simulation_review.status == "completed"
                    else [],
                    hypothesis.review.simulation_review.steps
                    if hypothesis.review.simulation_review.status == "completed"
                    else [],
                )
            ),
        ),
        review_sections=_build_review_sections(hypothesis.review),
        island_id=hypothesis.island_id,
        island_alias=island_aliases.get(
            hypothesis.island_id, hypothesis.island_id[:8] if hypothesis.island_id else ""
        ),
        parent_ids=list(hypothesis.parent_ids),
        parent_aliases=[hypothesis_aliases.get(parent_id, parent_id[:8]) for parent_id in hypothesis.parent_ids],
    )


def _build_metrics(state: CoScientistStateContract) -> list[MetricItem]:
    return [
        MetricItem(label="Hypotheses", value=len(state.hypotheses), tone="blue"),
        MetricItem(label="Islands", value=len(state.islands), tone="green"),
        MetricItem(label="Iterations", value=state.iteration_count, tone="amber"),
        MetricItem(label="Convergence", value=state.convergence_count, tone="violet"),
    ]


def _build_hypothesis_aliases(state: CoScientistStateContract) -> dict[str, str]:
    ordered = sorted(state.hypotheses.values(), key=lambda item: item.timestamp)
    return {hypothesis.id: f"H{index:04d}" for index, hypothesis in enumerate(ordered, start=1)}


def _build_island_aliases(state: CoScientistStateContract) -> dict[str, str]:
    ordered = sorted(state.islands.values(), key=lambda item: item.id)
    return {island.id: f"I{index:03d}" for index, island in enumerate(ordered, start=1)}


def _build_ranking(state: CoScientistStateContract, aliases: dict[str, str]) -> list[RankingItem]:
    viable = [hypothesis for hypothesis in state.hypotheses.values() if hypothesis.is_viable]
    viable.sort(key=lambda item: item.elo_rating, reverse=True)

    ranking_items: list[RankingItem] = []
    for index, hypothesis in enumerate(viable, start=1):
        ranking_items.append(
            RankingItem(
                id=hypothesis.id,
                rank=index,
                title=f"{aliases.get(hypothesis.id, hypothesis.id[:8])} - {hypothesis.origin.content.summary}",
                subtitle=hypothesis.origin.content.category or hypothesis.origin.strategy.replace("_", " "),
                elo=round(hypothesis.elo_rating),
                tone=_RANKING_TONES[(index - 1) % len(_RANKING_TONES)],
            )
        )
    return ranking_items


def _build_graph_seed(
    state: CoScientistStateContract,
    hypothesis_aliases: dict[str, str],
    island_aliases: dict[str, str],
) -> GraphSeed:
    nodes_by_island: dict[str, list[GraphSeedNode]] = defaultdict(list)
    local_edges_by_island: dict[str, list[GraphSeedEdge]] = defaultdict(list)
    cross_edges: list[GraphSeedEdge] = []

    island_hypothesis_ids = Counter(
        hypothesis.island_id
        for hypothesis in state.hypotheses.values()
        if hypothesis.island_id and hypothesis.is_viable
    )

    for hypothesis in sorted(state.hypotheses.values(), key=lambda item: item.elo_rating, reverse=True):
        if not hypothesis.is_viable:
            continue
        island_id = hypothesis.island_id
        if not island_id:
            continue
        nodes_by_island[island_id].append(
            GraphSeedNode(
                id=hypothesis.id,
                label=hypothesis_aliases.get(hypothesis.id, hypothesis.id[:8]),
                score=round(hypothesis.elo_rating),
            )
        )
        for parent_id in hypothesis.parent_ids:
            if parent_id not in state.hypotheses:
                continue
            parent = state.hypotheses[parent_id]
            edge = GraphSeedEdge(id=f"{parent_id}->{hypothesis.id}", from_id=parent_id, to_id=hypothesis.id)
            if parent.island_id == island_id:
                local_edges_by_island[island_id].append(edge)
            else:
                cross_edges.append(edge)

    graph_islands: list[GraphSeedIsland] = []
    for island in sorted(state.islands.values(), key=lambda item: island_aliases.get(item.id, item.id)):
        node_items = nodes_by_island.get(island.id, [])
        if not node_items and island_hypothesis_ids.get(island.id, 0) == 0:
            continue
        graph_islands.append(
            GraphSeedIsland(
                id=island.id,
                nodes=node_items,
                edges=local_edges_by_island.get(island.id, []),
                metrics=GraphSeedIslandMetrics(
                    id=island.id,
                    alias=island_aliases.get(island.id, island.id[:8]),
                    decayedReward=round(island.decayed_reward, 3),
                    decayedVisits=round(island.decayed_visits, 3),
                    visitCount=island.visit_count,
                ),
            )
        )

    return GraphSeed(islands=graph_islands, crossEdges=cross_edges)


def _build_insight_sections(state: CoScientistStateContract) -> list[InsightSection]:
    insights = state.meta_review.insights_from_reviews
    overview = state.meta_review.research_overview
    insight_items = (
        insights.content
        if insights.status == "completed" and insights.content
        else ["No review insights available yet."]
    )
    overview_items = (
        [overview.content]
        if overview.status == "completed" and overview.content
        else ["No research overview available yet."]
    )
    return [
        InsightSection(
            title="Insights From Reviews",
            badge="Synthesized" if insights.status == "completed" else "In Review",
            icon="message-square",
            items=insight_items,
        ),
        InsightSection(
            title="Research Overview",
            badge="Complete" if overview.status == "completed" else "In Review",
            icon="book-open",
            items=overview_items,
        ),
        InsightSection(
            title="Iteration Strategy",
            badge="Pending",
            icon="brain",
            items=["See routing artifacts and evolution state for iteration-policy details."],
        ),
    ]


def _build_initial_review_summary(hypothesis: HypothesisContract) -> str:
    review = hypothesis.review.initial_review
    if review.status != "completed":
        return "Pending"
    verdict = "Passed" if review.passed else "Failed"
    bullet_count = len(review.preferences) + len(review.constraints)
    return f"{verdict} initial gate with {bullet_count} evaluation points."


def _build_full_review_summary(hypothesis: HypothesisContract) -> str:
    review = hypothesis.review.full_review
    if review.status != "completed":
        return "Pending"
    bullet_count = len(review.preferences) + len(review.constraints)
    return f"Captured {bullet_count} literature-grounded review points."


def _build_deep_verification_summary(assumptions: list[ReviewedAssumptionContract]) -> str:
    if not assumptions:
        return "Pending"
    flattened = _flatten_assumptions(assumptions)
    return f"Evaluated {len(flattened)} assumptions."


def _build_observation_summary(observations: list[ObservationContract]) -> str:
    if not observations:
        return "Pending"
    verdicts = Counter(observation.conclusion for observation in observations)
    lead_label, lead_count = verdicts.most_common(1)[0]
    return f"{len(observations)} observations reviewed; dominant outcome: {lead_label} ({lead_count})."


def _build_simulation_summary(failure_scenarios: list[str], steps: list[str]) -> str:
    if not failure_scenarios and not steps:
        return "Pending"
    return f"{len(steps)} simulation steps, {len(failure_scenarios)} failure scenarios."


def _flatten_assumptions(assumptions: list[ReviewedAssumptionContract], depth: int = 0) -> list[str]:
    flattened: list[str] = []
    for assumption in assumptions:
        prefix = "  " * depth
        correctness = f" [{assumption.correctness}]" if assumption.correctness else ""
        flattened.append(f"{prefix}{assumption.statement}{correctness}")
        if assumption.sub_assumptions:
            flattened.extend(_flatten_assumptions(assumption.sub_assumptions, depth + 1))
    return flattened


def _build_review_sections(review: ReviewContract) -> list[DashboardReviewSection]:
    sections: list[DashboardReviewSection] = []

    initial_review = review.initial_review
    if initial_review.status == "completed":
        sections.append(
            DashboardReviewSection(
                key="initial_review",
                title="Initial Review",
                verdict="PASS" if initial_review.passed else "FAIL",
                entries=[
                    DashboardReviewEntry(label="Preferences", items=initial_review.preferences),
                    DashboardReviewEntry(label="Constraints", items=initial_review.constraints),
                ],
            )
        )

    full_review = review.full_review
    if full_review.status == "completed":
        sections.append(
            DashboardReviewSection(
                key="full_review",
                title="Full Review",
                entries=[
                    DashboardReviewEntry(label="Preferences", items=full_review.preferences),
                    DashboardReviewEntry(label="Constraints", items=full_review.constraints),
                ],
            )
        )

    deep_verification = review.deep_verification_review
    if deep_verification.status == "completed":
        sections.append(
            DashboardReviewSection(
                key="deep_verification_review",
                title="Deep Verification",
                entries=[
                    DashboardReviewEntry(
                        label="Assumptions", items=_flatten_assumptions(deep_verification.assumptions)
                    )
                ],
            )
        )

    observation_review = review.observation_review
    if observation_review.status == "completed":
        sections.append(
            DashboardReviewSection(
                key="observation_review",
                title="Observation Review",
                entries=[
                    DashboardReviewEntry(
                        label="Observations",
                        items=[
                            f"[{observation.conclusion}] {observation.reasoning}"
                            for observation in observation_review.observations
                        ],
                    )
                ],
            )
        )

    simulation_review = review.simulation_review
    if simulation_review.status == "completed":
        sections.append(
            DashboardReviewSection(
                key="simulation_review",
                title="Simulation Review",
                entries=[
                    DashboardReviewEntry(label="Steps", items=simulation_review.steps),
                    DashboardReviewEntry(label="Failure Scenarios", items=simulation_review.failure_scenarios),
                ],
            )
        )

    review_summary = review.review_summary
    if review_summary.status == "completed":
        sections.append(
            DashboardReviewSection(
                key="review_summary",
                title="Review Summary",
                entries=[DashboardReviewEntry(label="Summary", items=review_summary.summaries)],
            )
        )

    return sections
