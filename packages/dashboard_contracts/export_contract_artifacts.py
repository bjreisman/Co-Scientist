"""Export dashboard contracts as JSON schema and generated frontend TypeScript."""

from __future__ import annotations

import json
from pathlib import Path

from packages.agent_support.pipeline_semantics import PIPELINE_STAGES

from .dashboard import DashboardSnapshot, RunProgress, RunSummary


SCHEMA_MODELS = {
    "dashboard_snapshot.schema.json": DashboardSnapshot,
    "run_progress.schema.json": RunProgress,
    "run_summary.schema.json": RunSummary,
}


def render_frontend_types() -> str:
    """Render generated frontend TypeScript for dashboard-facing shared contracts."""
    pipeline_stage_literals = ", ".join(f"'{stage}'" for stage in PIPELINE_STAGES)
    return """/* eslint-disable */
// This file is generated from packages/dashboard_contracts/dashboard.py.
// Do not edit by hand; update the shared dashboard contracts and regenerate instead.

export interface HypothesisContent {
  statement: string
  mechanism: string
  experimental_design: string
  summary: string
  category: string
}

export interface Origin {
  strategy: string
  content: HypothesisContent
}

export interface ReviewGate {
  passed?: boolean | null
  summary: string
}

export interface ReviewEntry {
  label: string
  content: string
  items: string[]
}

export interface ReviewSection {
  key: string
  title: string
  verdict?: string | null
  entries: ReviewEntry[]
}

export interface ReviewBundle {
  initial_review: ReviewGate
  full_review: ReviewGate
  deep_verification_review: ReviewGate
  observation_review: ReviewGate
  simulation_review: ReviewGate
}

export interface RunPolicySettings {
  exploration_mode: 'conservative' | 'balanced' | 'aggressive'
  generation_bias: 'literature_heavy' | 'debate_heavy' | 'assumptions_heavy' | 'mixed'
  review_rigor: 'light' | 'standard' | 'strict'
  evolution_style: 'exploit' | 'balanced' | 'diversify'
  budget_profile: 'low' | 'medium' | 'high'
  stop_policy: 'exploratory' | 'standard' | 'strict'
  iteration_policy: 'completion_driven' | 'capped'
  iteration_band?: '6_10' | '10_14' | '15_20' | '20_30' | null
  allowed_generation_strategies: (
    'literature_exploration_generation' |
    'scientific_debates_generation' |
    'assumptions_identification_generation'
  )[]
  allowed_review_modes: (
    'full_review' |
    'deep_verification_review' |
    'observation_review' |
    'simulation_review'
  )[]
  human_checkpoint: 'auto' | 'before_overview' | 'before_completion' | 'every_major_stage'
}

export interface PolicyDecision {
  status: 'draft' | 'completed' | 'overridden'
  run_id: string
  policy: RunPolicySettings
  rationale: string[]
  updated_at: string
}

export interface ResolvedGenerationConfig {
  num_debaters: number
  max_debate_turns: number
}

export interface ResolvedIslandConfig {
  ucb_exploration_constant: number
  decay_factor: number
  softmax_temperature: number
  stagnation_epsilon: number
}

export interface ResolvedRankingConfig {
  placement_match_count: number
  tournament_top_k: number
  elo_k_factor: number
}

export interface ResolvedConvergenceConfig {
  convergence_count_threshold: number
  max_iterations: number
  safety_max_iterations: number
  iteration_cap_source: (
    'completion_driven_default' |
    'iteration_band' |
    'legacy_budget_profile' |
    'config_override'
  )
}

export interface ResolvedProximityConfig {
  enabled: boolean
  provider: string
  model: string
  dimensions: number
  base_url_env: string
  api_key_env: string
  timeout_seconds: number
}

export interface ResolvedRunConfig {
  profile: 'conservative' | 'balanced' | 'aggressive'
  generation: ResolvedGenerationConfig
  island: ResolvedIslandConfig
  ranking: ResolvedRankingConfig
  convergence: ResolvedConvergenceConfig
  proximity: ResolvedProximityConfig
  updated_at: string
}

export interface StrategyPlan {
  status: 'planned' | 'running' | 'completed' | 'blocked'
  current_phase: (
    'Generation' |
    'Reflection' |
    'Insights from Reviews' |
    'Proximity' |
    'Ranking' |
    'Evolution' |
    'Research Overview' |
    'Configuration'
  )
  next_action: (
    'run_configuration' |
    'run_generation' |
    'run_review' |
    'run_insights' |
    'run_proximity' |
    'run_ranking' |
    'continue_evolution' |
    'return_to_generation' |
    'generate_overview' |
    'inspect_state'
  )
  selected_generation_strategies: (
    'literature_exploration_generation' |
    'scientific_debates_generation' |
    'assumptions_identification_generation'
  )[]
  selected_evolution_strategies: string[]
  max_new_hypotheses: number
  reasoning: string[]
  advisory_recommendation: string
  signals: Record<string, unknown>
  updated_at: string
}

export interface StrategyDecisionRecord extends StrategyPlan {
  run_id: string
  decision_index: number
}

export interface DashboardRoutingArtifacts {
  policy_decision: PolicyDecision | null
  resolved_config: ResolvedRunConfig | null
  strategy_plan: StrategyPlan | null
  latest_strategy_decision: StrategyDecisionRecord | null
  strategy_decision_count: number
}

export interface Hypothesis {
  id: string
  alias: string
  timestamp: string
  elo_rating: number
  origin: Origin
  review: ReviewBundle
  review_sections: ReviewSection[]
  island_id: string
  island_alias: string
  parent_ids: string[]
  parent_aliases: string[]
}

export interface ResearchPlan {
  research_goal: string
  preferences: string[]
  constraints: string[]
}

export interface IslandState {
  id: string
  alias: string
  decayed_reward: number
  decayed_visits: number
  visit_count: number
}

export interface CoScientistState {
  research_plan: ResearchPlan
  hypotheses: Record<string, Hypothesis>
  islands: Record<string, IslandState>
  iteration_count: number
  convergence_count: number
}

export interface RankingItem {
  id: string
  rank: number
  title: string
  subtitle: string
  elo: number
  tone: 'blue' | 'violet' | 'cyan'
}

export interface MetricItem {
  label: string
  value: number
  tone: 'blue' | 'green' | 'amber' | 'violet'
}

export interface GraphSeedEdge {
  id: string
  from: string
  to: string
}

export interface GraphSeedNode {
  id: string
  label: string
  score: number
}

export interface GraphSeedIslandMetrics {
  id: string
  alias: string
  decayedReward: number
  decayedVisits: number
  visitCount: number
}

export interface GraphSeedIsland {
  id: string
  nodes: GraphSeedNode[]
  edges: GraphSeedEdge[]
  metrics: GraphSeedIslandMetrics
}

export interface GraphSeed {
  islands: GraphSeedIsland[]
  crossEdges: GraphSeedEdge[]
}

export interface InsightSection {
  title: string
  badge: string
  icon: string
  items: string[]
}

export interface RunSummary {
  runId: string
  updatedAt: string
  hasDatabase: boolean
  hasSnapshot: boolean
}

export const PIPELINE_STAGES = [__PIPELINE_STAGE_LITERALS__] as const
export type PipelineStage = (typeof PIPELINE_STAGES)[number]
export type RunProgressSource =
  | 'current_skill'
  | 'current_stage'
  | 'current_phase'
  | 'strategy_plan'
  | 'artifact_inference'
export type RunProgressConfidence = 'high' | 'medium' | 'low'

export interface RunProgress {
  runId: string
  currentStage: PipelineStage
  stageTrail: PipelineStage[]
  completedStages: PipelineStage[]
  plannedNextStage?: PipelineStage | null
  currentSkill: string
  source: RunProgressSource
  confidence: RunProgressConfidence
}

export interface DashboardSnapshot {
  runId: string
  updatedAt: string
  hasData: boolean
  state: CoScientistState
  metrics: MetricItem[]
  ranking: RankingItem[]
  graphSeed: GraphSeed
  insightSections: InsightSection[]
  routing: DashboardRoutingArtifacts
}
""".replace("__PIPELINE_STAGE_LITERALS__", pipeline_stage_literals)


def export_dashboard_contract_artifacts(root: Path | None = None) -> list[Path]:
    """Write dashboard JSON schema files and generated frontend contract types."""
    package_root = root or Path(__file__).resolve().parent
    repo_root = package_root.parents[1]
    schema_root = package_root / "schema"
    schema_root.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for filename, model in SCHEMA_MODELS.items():
        path = schema_root / filename
        path.write_text(
            json.dumps(model.model_json_schema(by_alias=True), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)

    frontend_types_path = repo_root / "apps" / "dashboard" / "app" / "types" / "generated" / "dashboard.ts"
    frontend_types_path.parent.mkdir(parents=True, exist_ok=True)
    frontend_types_path.write_text(render_frontend_types(), encoding="utf-8")
    written.append(frontend_types_path)
    return written


if __name__ == "__main__":
    export_dashboard_contract_artifacts()
