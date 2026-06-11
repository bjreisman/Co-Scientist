export { PIPELINE_STAGES } from './generated/dashboard'

export type {
  CoScientistState,
  DashboardRoutingArtifacts,
  DashboardSnapshot,
  GraphSeed,
  GraphSeedEdge,
  GraphSeedIsland,
  GraphSeedIslandMetrics,
  GraphSeedNode,
  Hypothesis,
  HypothesisContent,
  InsightSection,
  IslandState,
  MetricItem,
  Origin,
  PipelineStage,
  PolicyDecision,
  RankingItem,
  ResolvedRunConfig,
  ResearchPlan,
  ReviewBundle,
  ReviewEntry,
  ReviewGate,
  ReviewSection,
  RunProgress,
  RunSummary,
  StrategyDecisionRecord,
  StrategyPlan
} from './generated/dashboard'

export interface GraphLine {
  id: string
  x: number
  y: number
  width: number
  rotation: number
  color: string
  variant?: 'intra' | 'cross'
}

export interface GraphArrow {
  id: string
  x: number
  y: number
  rotation: number
  color: string
  variant?: 'intra' | 'cross'
}

export interface GraphNode {
  id: string
  x: number
  y: number
  label: string
  score: number
  tone: string
  width?: number
  height?: number
}

export interface GraphEdge {
  id: string
  from: string
  to: string
  color: string
  variant?: 'intra' | 'cross'
}

export interface GraphIsland {
  id: string
  x: number
  y: number
  width: number
  height: number
  tone: 'blue' | 'violet'
  lines: GraphLine[]
  arrows: GraphArrow[]
  edges?: GraphEdge[]
  lineOffset?: {
    x?: number
    y?: number
  }
  nodes: GraphNode[]
  metrics: {
    x: number
    y: number
    lines: string[]
  }
}

export interface GraphData {
  islands: GraphIsland[]
  crossLines: GraphLine[]
  crossArrows: GraphArrow[]
  crossEdges?: GraphEdge[]
}
