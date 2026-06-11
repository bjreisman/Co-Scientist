"""Dashboard response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from packages.agent_contracts import (
    PolicyDecisionContract,
    ResolvedRunConfigContract,
    StrategyDecisionRecordContract,
    StrategyPlanContract,
)
from packages.agent_support.pipeline_semantics import PipelineStage


class RunSummary(BaseModel):
    """Metadata for an available run."""

    runId: str
    updatedAt: str
    hasDatabase: bool
    hasSnapshot: bool


RunProgressSource = Literal[
    "current_skill",
    "current_stage",
    "current_phase",
    "strategy_plan",
    "artifact_inference",
]

RunProgressConfidence = Literal["high", "medium", "low"]


class RunProgress(BaseModel):
    """Current pipeline stage for a run."""

    runId: str
    currentStage: PipelineStage
    stageTrail: list[PipelineStage] = Field(default_factory=list)
    completedStages: list[PipelineStage] = Field(default_factory=list)
    plannedNextStage: PipelineStage | None = None
    currentSkill: str = ""
    source: RunProgressSource = "artifact_inference"
    confidence: RunProgressConfidence = "low"


class DashboardReviewGate(BaseModel):
    """Compact review summary for the dashboard."""

    passed: bool | None = None
    summary: str = ""


class DashboardReviewEntry(BaseModel):
    """A labeled review subsection rendered in the detail panel."""

    label: str
    content: str = ""
    items: list[str] = Field(default_factory=list)


class DashboardReviewSection(BaseModel):
    """A formatted review section following shared review formatting rules."""

    key: str
    title: str
    verdict: str | None = None
    entries: list[DashboardReviewEntry] = Field(default_factory=list)


class DashboardReviewBundle(BaseModel):
    """Review summaries rendered by the hypothesis detail panel."""

    initial_review: DashboardReviewGate = Field(default_factory=DashboardReviewGate)
    full_review: DashboardReviewGate = Field(default_factory=DashboardReviewGate)
    deep_verification_review: DashboardReviewGate = Field(default_factory=DashboardReviewGate)
    observation_review: DashboardReviewGate = Field(default_factory=DashboardReviewGate)
    simulation_review: DashboardReviewGate = Field(default_factory=DashboardReviewGate)


class DashboardHypothesisContent(BaseModel):
    """Dashboard-facing hypothesis content."""

    statement: str = ""
    mechanism: str = ""
    experimental_design: str = ""
    summary: str = ""
    category: str = ""


class DashboardOrigin(BaseModel):
    """Dashboard-facing hypothesis origin."""

    strategy: str = ""
    content: DashboardHypothesisContent = Field(default_factory=DashboardHypothesisContent)


class DashboardHypothesis(BaseModel):
    """Dashboard-facing hypothesis state."""

    id: str
    alias: str
    timestamp: str
    elo_rating: int
    origin: DashboardOrigin
    review: DashboardReviewBundle = Field(default_factory=DashboardReviewBundle)
    review_sections: list[DashboardReviewSection] = Field(default_factory=list)
    island_id: str = ""
    island_alias: str = ""
    parent_ids: list[str] = Field(default_factory=list)
    parent_aliases: list[str] = Field(default_factory=list)


class DashboardResearchPlan(BaseModel):
    """Dashboard-facing research plan."""

    research_goal: str = ""
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class DashboardIslandState(BaseModel):
    """Dashboard-facing island state."""

    id: str
    alias: str
    decayed_reward: float
    decayed_visits: float
    visit_count: int


class DashboardState(BaseModel):
    """Dashboard-facing system state."""

    research_plan: DashboardResearchPlan = Field(default_factory=DashboardResearchPlan)
    hypotheses: dict[str, DashboardHypothesis] = Field(default_factory=dict)
    islands: dict[str, DashboardIslandState] = Field(default_factory=dict)
    iteration_count: int = 0
    convergence_count: int = 0


class MetricItem(BaseModel):
    """Top-bar metric."""

    label: str
    value: int
    tone: Literal["blue", "green", "amber", "violet"]


class RankingItem(BaseModel):
    """Ranking list item."""

    id: str
    rank: int
    title: str
    subtitle: str
    elo: int
    tone: Literal["blue", "violet", "cyan"]


class GraphSeedEdge(BaseModel):
    """Logical graph edge."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")


class GraphSeedNode(BaseModel):
    """Logical graph node."""

    id: str
    label: str
    score: int


class GraphSeedIslandMetrics(BaseModel):
    """Island metrics shown in the graph."""

    id: str
    alias: str
    decayedReward: float
    decayedVisits: float
    visitCount: int


class GraphSeedIsland(BaseModel):
    """Logical graph island."""

    id: str
    nodes: list[GraphSeedNode] = Field(default_factory=list)
    edges: list[GraphSeedEdge] = Field(default_factory=list)
    metrics: GraphSeedIslandMetrics


class GraphSeed(BaseModel):
    """Logical graph seed returned by the snapshot projection."""

    islands: list[GraphSeedIsland] = Field(default_factory=list)
    crossEdges: list[GraphSeedEdge] = Field(default_factory=list)


class InsightSection(BaseModel):
    """Meta-review card content."""

    title: str
    badge: str
    icon: str
    items: list[str] = Field(default_factory=list)


class DashboardRoutingArtifacts(BaseModel):
    """Policy and routing artifacts surfaced in the dashboard."""

    policy_decision: PolicyDecisionContract | None = None
    resolved_config: ResolvedRunConfigContract | None = None
    strategy_plan: StrategyPlanContract | None = None
    latest_strategy_decision: StrategyDecisionRecordContract | None = None
    strategy_decision_count: int = 0


class DashboardSnapshot(BaseModel):
    """Complete dashboard snapshot."""

    runId: str
    updatedAt: str
    hasData: bool
    state: DashboardState
    metrics: list[MetricItem] = Field(default_factory=list)
    ranking: list[RankingItem] = Field(default_factory=list)
    graphSeed: GraphSeed = Field(default_factory=GraphSeed)
    insightSections: list[InsightSection] = Field(default_factory=list)
    routing: DashboardRoutingArtifacts = Field(default_factory=DashboardRoutingArtifacts)
