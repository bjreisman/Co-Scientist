import { readdir, readFile, stat } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { createError } from 'h3'
import { PIPELINE_STAGES, type CoScientistState, type DashboardRoutingArtifacts, type DashboardSnapshot, type PipelineStage, type RunProgress, type RunSummary } from '~/types/coScientist'

const knownStages = new Set<string>(PIPELINE_STAGES)
const rankingTones = ['blue', 'violet', 'cyan'] as const

type StageArtifact = {
  runId?: string
  stage?: string
  stageTrail?: string[]
  updatedAt?: string
}

type PipelineStateArtifact = {
  iteration?: number
  iterationCount?: number
  convergence_count?: number
  convergenceCount?: number
  updated_at?: string
  updatedAt?: string
  currentPhase?: string
  currentSkill?: string
  stageTrail?: string[]
  topHypothesisIds?: string[]
  hypothesisCount?: number
  viableHypothesisCount?: number
  status?: string
}

type StrategyPlanArtifact = {
  current_phase?: string
  next_action?: string
  status?: string
}

type EvolutionStateArtifact = {
  status?: string
  iterationCount?: number
  convergenceCount?: number
  convergenceThreshold?: number
  stopReason?: string
  lastSelectedIsland?: string
  lastSelectedStrategy?: string
  enteredTopKLastRound?: boolean | null
}

type CompletionDecisionArtifact = {
  decision?: string
}

type RawResearchPlanArtifact = {
  research_goal?: string
  preferences?: string[]
  constraints?: string[]
}

type RawHypothesisArtifact = {
  id?: string
  placement_match_ids?: string[]
  ranked_match_ids?: string[]
  content?: {
    statement?: string
    mechanism?: string
    experimental_design?: string[] | string
    summary?: string
    category?: string
  }
  origin?: {
    strategy?: string
    content?: {
      statement?: string
      mechanism?: string
      experimental_design?: string[] | string
      summary?: string
      category?: string
    }
  }
  created_at?: string
  timestamp?: string
  parent_id?: string
  parent_ids?: string[]
  island_id?: string
  elo_rating?: number
  evolution_type?: string
  review?: {
    initial_review?: RawInitialReviewArtifact
    full_review?: RawFullReviewArtifact
    deep_verification_review?: RawDeepVerificationReviewArtifact
    observation_review?: RawObservationReviewArtifact
    simulation_review?: RawSimulationReviewArtifact
    review_summary?: RawReviewSummaryArtifact
  }
}

type RawOriginArtifact = {
  strategy?: string
}

type RawInitialReviewArtifact = {
  status?: string
  passed?: boolean
  preferences?: string[]
  constraints?: string[]
  summary?: string
}

type RawFullReviewArtifact = {
  status?: string
  preferences?: string[]
  constraints?: string[]
  overall_assessment?: string
  summary?: string
  score?: number
  retrieval_results?: unknown[]
}

type RawReviewedAssumptionArtifact = {
  statement?: string
  correctness?: string
  sub_assumptions?: RawReviewedAssumptionArtifact[]
}

type RawDeepVerificationReviewArtifact = {
  status?: string
  assumptions?: RawReviewedAssumptionArtifact[]
}

type RawObservationArtifact = {
  reasoning?: string
  conclusion?: string
}

type RawObservationReviewArtifact = {
  status?: string
  observations?: RawObservationArtifact[]
  retrieval_results?: unknown[]
}

type RawSimulationReviewArtifact = {
  status?: string
  steps?: string[]
  failure_scenarios?: string[]
}

type RawReviewSummaryArtifact = {
  status?: string
  summaries?: string[]
}

type RawTournamentRating = {
  elo?: number
}

type RawTournamentArtifact = {
  iteration?: number
  created_at?: string
  top_k_ids?: string[]
  updated_ratings?: Record<string, RawTournamentRating>
}

type RawIslandArtifact = {
  id?: string
  decayed_reward?: number
  decayed_visits?: number
  visit_count?: number
}

type RawIslandsArtifact = {
  items?: RawIslandArtifact[]
}

type HypothesisRecord = CoScientistState['hypotheses'][string]
type ReviewBundleRecord = HypothesisRecord['review']
type ReviewSectionRecord = HypothesisRecord['review_sections'][number]

const emptyState = (): CoScientistState => ({
  research_plan: {
    research_goal: '',
    preferences: [],
    constraints: []
  },
  hypotheses: {},
  islands: {},
  iteration_count: 0,
  convergence_count: 0
})

const emptyRouting = (): DashboardRoutingArtifacts => ({
  policy_decision: null,
  resolved_config: null,
  strategy_plan: null,
  latest_strategy_decision: null,
  strategy_decision_count: 0
})

const buildEmptySnapshot = (runId: string, updatedAt: string): DashboardSnapshot => ({
  runId,
  updatedAt,
  hasData: false,
  state: emptyState(),
  metrics: [
    { label: 'Hypotheses', value: 0, tone: 'blue' },
    { label: 'Islands', value: 0, tone: 'green' },
    { label: 'Iterations', value: 0, tone: 'amber' },
    { label: 'Convergence', value: 0, tone: 'violet' }
  ],
  ranking: [],
  graphSeed: {
    islands: [],
    crossEdges: []
  },
  insightSections: [
    {
      title: 'Insights From Reviews',
      badge: 'Synthesized',
      icon: 'message-square',
      items: ['No review insights available yet.']
    },
    {
      title: 'Research Overview',
      badge: 'In Review',
      icon: 'book-open',
      items: ['No research overview available yet.']
    },
    {
      title: 'Iteration Strategy',
      badge: 'Pending',
      icon: 'brain',
      items: ['No iteration strategy summary available yet.']
    }
  ],
  routing: emptyRouting()
})

const normalizeStage = (value: string | undefined): PipelineStage => {
  if (value && knownStages.has(value as PipelineStage)) {
    return value as PipelineStage
  }
  return 'Idle'
}

const normalizeStageTrail = (value: string[] | undefined): PipelineStage[] =>
  (value ?? []).filter((stage): stage is PipelineStage => knownStages.has(stage as PipelineStage))

const pipelineDisplayOrder: PipelineStage[] = [
  'Bootstrap',
  'Configuration',
  'Generation',
  'Evolution',
  'Reflection',
  'Insights from Reviews',
  'Proximity',
  'Ranking',
  'Research Overview'
]

const terminalStages = new Set<PipelineStage>(['Completed', 'Failed'])

const trackedFlowStages = new Set<PipelineStage>([
  'Bootstrap',
  'Configuration',
  'Generation',
  'Evolution',
  'Reflection',
  'Insights from Reviews',
  'Proximity',
  'Ranking',
  'Research Overview'
])

const stageForSkill = (value: string | undefined): PipelineStage | undefined => {
  switch (value) {
    case 'research-config':
      return 'Configuration'
    case 'hypothesis-generation-pipeline':
      return 'Generation'
    case 'hypothesis-evolution-loop':
      return 'Evolution'
    case 'hypothesis-review-pipeline':
      return 'Reflection'
    case 'insights-from-reviews':
      return 'Insights from Reviews'
    case 'hypothesis-proximity-update':
      return 'Proximity'
    case 'hypothesis-ranking-pipeline':
      return 'Ranking'
    case 'research-overview-pipeline':
      return 'Research Overview'
    default:
      return undefined
  }
}

const stageForNextAction = (value: string | undefined): PipelineStage | undefined => {
  switch (value) {
    case 'run_configuration':
      return 'Configuration'
    case 'run_generation':
    case 'return_to_generation':
      return 'Generation'
    case 'run_review':
      return 'Reflection'
    case 'run_insights':
      return 'Insights from Reviews'
    case 'run_proximity':
      return 'Proximity'
    case 'run_ranking':
      return 'Ranking'
    case 'generate_overview':
      return 'Research Overview'
    case 'continue_evolution':
      return 'Evolution'
    default:
      return undefined
  }
}

const mergeStageEvidence = (...lists: PipelineStage[][]): PipelineStage[] => {
  const seen = new Set<PipelineStage>()
  const merged: PipelineStage[] = []
  for (const list of lists) {
    for (const stage of list) {
      if (!trackedFlowStages.has(stage) || seen.has(stage)) {
        continue
      }
      seen.add(stage)
      merged.push(stage)
    }
  }
  return pipelineDisplayOrder.filter((stage) => merged.includes(stage))
}

const pathExists = async (path: string): Promise<boolean> => {
  try {
    await stat(path)
    return true
  } catch (error) {
    if (typeof error === 'object' && error && 'code' in error && error.code === 'ENOENT') {
      return false
    }
    throw error
  }
}

const readHypothesisProgressSignals = async (runDir: string): Promise<{
  hasReviewArtifacts: boolean
  hasRankingArtifacts: boolean
}> => {
  const hypothesesDir = join(runDir, 'hypotheses')
  let hasReviewArtifacts = false
  let hasRankingArtifacts = false
  try {
    const entries = await readdir(hypothesesDir, { withFileTypes: true })
    await Promise.all(
      entries
        .filter((entry) => entry.isDirectory())
        .map(async (entry) => {
          const [reviewExists, hypothesis] = await Promise.all([
            pathExists(join(hypothesesDir, entry.name, 'REVIEW', 'INITIAL_REVIEW.json')),
            readJson<RawHypothesisArtifact>(join(hypothesesDir, entry.name, 'HYPOTHESIS.json'))
          ])
          if (reviewExists) {
            hasReviewArtifacts = true
          }
          if ((hypothesis?.placement_match_ids?.length ?? 0) > 0 || (hypothesis?.ranked_match_ids?.length ?? 0) > 0) {
            hasRankingArtifacts = true
          }
        })
    )
    return { hasReviewArtifacts, hasRankingArtifacts }
  } catch (error) {
    if (typeof error === 'object' && error && 'code' in error && error.code === 'ENOENT') {
      return { hasReviewArtifacts: false, hasRankingArtifacts: false }
    }
    throw error
  }
}

const inferProgressFromArtifacts = async (
  runDir: string,
  currentStageArtifact?: StageArtifact,
  pipelineState?: PipelineStateArtifact,
  strategyPlan?: StrategyPlanArtifact,
): Promise<RunProgress> => {
  const currentStage = normalizeStage(currentStageArtifact?.stage)
  const pipelinePhase = normalizeStage(pipelineState?.currentPhase)
  const strategyPhase = normalizeStage(strategyPlan?.current_phase)
  const skillStage = stageForSkill(pipelineState?.currentSkill)
  const nextActionStage = stageForNextAction(strategyPlan?.next_action)
  const currentSkill = typeof pipelineState?.currentSkill === 'string' ? pipelineState.currentSkill : ''
  const pipelineStatus = pipelineState?.status ?? ''
  const strategyStatus = strategyPlan?.status ?? ''

  const preservedTerminalStage = terminalStages.has(currentStage) ? currentStage : undefined
  const [{ hasReviewArtifacts, hasRankingArtifacts }, hasInsightsArtifact, hasOverviewArtifact, hasProximityGraph] = await Promise.all([
    readHypothesisProgressSignals(runDir),
    pathExists(join(runDir, 'meta', 'INSIGHTS_FROM_REVIEWS.json')),
    pathExists(join(runDir, 'meta', 'RESEARCH_OVERVIEW.json')),
    pathExists(join(runDir, 'state', 'PROXIMITY_GRAPH.json'))
  ])
  const inferredCompletedStages: PipelineStage[] = []

  if (hasReviewArtifacts) {
    inferredCompletedStages.push('Reflection')
  }
  if (hasInsightsArtifact) {
    inferredCompletedStages.push('Insights from Reviews')
  }
  if (hasProximityGraph) {
    inferredCompletedStages.push('Proximity')
  }
  if (hasRankingArtifacts) {
    inferredCompletedStages.push('Ranking')
  }
  if (hasOverviewArtifact) {
    inferredCompletedStages.push('Research Overview')
  }

  const historicalStageEvidence = mergeStageEvidence(
    normalizeStageTrail(currentStageArtifact?.stageTrail),
    normalizeStageTrail(pipelineState?.stageTrail),
    inferredCompletedStages
  )

  const inferredCurrentSignal = [
    {
      stage: skillStage,
      source: 'current_skill' as RunProgress['source'],
      confidence: 'high' as RunProgress['confidence']
    },
    {
      stage: currentStage,
      source: 'current_stage' as RunProgress['source'],
      confidence: 'high' as RunProgress['confidence']
    },
    {
      stage: pipelinePhase,
      source: 'current_phase' as RunProgress['source'],
      confidence: 'medium' as RunProgress['confidence']
    },
    {
      stage: strategyPhase,
      source: 'strategy_plan' as RunProgress['source'],
      confidence: 'low' as RunProgress['confidence']
    }
  ].find(
    (
      candidate
    ): candidate is {
      stage: PipelineStage
      source: RunProgress['source']
      confidence: RunProgress['confidence']
    } => Boolean(candidate.stage) && candidate.stage !== 'Idle' && !terminalStages.has(candidate.stage)
  )

  const inferredCurrentStage = preservedTerminalStage
    ?? inferredCurrentSignal?.stage
    ?? historicalStageEvidence[historicalStageEvidence.length - 1]
    ?? currentStage
  const progressSource = preservedTerminalStage
    ? 'current_stage'
    : (inferredCurrentSignal?.source ?? 'artifact_inference')
  const progressConfidence = preservedTerminalStage
    ? 'high'
    : (inferredCurrentSignal?.confidence ?? (completedStages.length > 0 ? 'low' : 'low'))
  const plannedNextStage = (
    !preservedTerminalStage
    && pipelineStatus !== 'completed'
    && strategyStatus !== 'completed'
    && nextActionStage
    && nextActionStage !== inferredCurrentStage
  )
    ? nextActionStage
    : null
  const completedStages = historicalStageEvidence.filter((stage) => stage !== inferredCurrentStage)
  const stageTrail = mergeStageEvidence(
    completedStages,
    inferredCurrentStage !== 'Idle' && !terminalStages.has(inferredCurrentStage) ? [inferredCurrentStage] : []
  )

  return {
    runId: currentStageArtifact?.runId ?? '',
    currentStage: inferredCurrentStage,
    stageTrail,
    completedStages,
    plannedNextStage,
    currentSkill,
    source: progressSource,
    confidence: progressConfidence
  }
}

const defaultRunsDir = () => resolve(process.cwd(), '..', '..', 'runs')

export const resolveRunsDir = () => resolve(process.env.CO_SCIENTIST_RUNS_DIR ?? defaultRunsDir())

const readJson = async <T>(path: string): Promise<T | undefined> => {
  try {
    return JSON.parse(await readFile(path, 'utf-8')) as T
  } catch (error) {
    if (typeof error === 'object' && error && 'code' in error && error.code === 'ENOENT') {
      return undefined
    }
    throw error
  }
}

const readJsonLines = async <T>(path: string): Promise<T[]> => {
  try {
    const content = await readFile(path, 'utf-8')
    return content
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as T)
  } catch (error) {
    if (typeof error === 'object' && error && 'code' in error && error.code === 'ENOENT') {
      return []
    }
    throw error
  }
}

const toStringList = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

const toFiniteNumber = (value: unknown, fallback = 0): number => {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

const hasCompletedStatus = (value: string | undefined) => value === 'completed'

const toExperimentalDesign = (value: string[] | string | undefined): string => {
  if (Array.isArray(value)) {
    return value.join('\n')
  }
  return typeof value === 'string' ? value : ''
}

const normalizeTimestamp = (value: string | undefined, fallback: string) => value ?? fallback

const buildReviewEntry = (label: string, items: string[], content = '') => ({
  label,
  content,
  items
})

const formatIterationBand = (value: string | null | undefined) => value ? value.replaceAll('_', '-') : ''

const flattenAssumptions = (assumptions: RawReviewedAssumptionArtifact[], depth = 0): string[] => {
  const items: string[] = []
  for (const assumption of assumptions) {
    const statement = assumption.statement?.trim()
    if (!statement) {
      continue
    }
    const correctness = assumption.correctness?.trim() ? ` [${assumption.correctness.trim()}]` : ''
    items.push(`${'  '.repeat(depth)}${statement}${correctness}`)
    items.push(...flattenAssumptions(assumption.sub_assumptions ?? [], depth + 1))
  }
  return items
}

const buildInitialReviewSummary = (review: RawInitialReviewArtifact): string => {
  if (!hasCompletedStatus(review.status)) {
    return 'Pending'
  }
  const verdict = review.passed ? 'Passed' : 'Failed'
  const bulletCount = toStringList(review.preferences).length + toStringList(review.constraints).length
  return `${verdict} initial gate with ${bulletCount} evaluation points.`
}

const buildFullReviewSummary = (review: RawFullReviewArtifact): string => {
  if (!hasCompletedStatus(review.status)) {
    return 'Pending'
  }
  const bulletCount = toStringList(review.preferences).length + toStringList(review.constraints).length
  return `Captured ${bulletCount} literature-grounded review points.`
}

const buildDeepVerificationSummary = (review: RawDeepVerificationReviewArtifact): string => {
  const flattened = flattenAssumptions(review.assumptions ?? [])
  return flattened.length ? `Evaluated ${flattened.length} assumptions.` : 'Pending'
}

const buildObservationSummary = (review: RawObservationReviewArtifact): string => {
  const observations = review.observations ?? []
  if (!observations.length) {
    return 'Pending'
  }
  const counts = new Map<string, number>()
  for (const observation of observations) {
    const key = observation.conclusion?.trim() || 'neutral'
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  let dominantLabel = 'neutral'
  let dominantCount = 0
  for (const [label, count] of counts.entries()) {
    if (count > dominantCount) {
      dominantLabel = label
      dominantCount = count
    }
  }
  return `${observations.length} observations reviewed; dominant outcome: ${dominantLabel} (${dominantCount}).`
}

const buildSimulationSummary = (review: RawSimulationReviewArtifact): string => {
  const steps = toStringList(review.steps)
  const failures = toStringList(review.failure_scenarios)
  if (!steps.length && !failures.length) {
    return 'Pending'
  }
  return `${steps.length} simulation steps, ${failures.length} failure scenarios.`
}

const mergeReviewArtifacts = (
  hypothesis: RawHypothesisArtifact,
  reviewArtifacts: {
    initialReview?: RawInitialReviewArtifact
    fullReview?: RawFullReviewArtifact
    deepVerificationReview?: RawDeepVerificationReviewArtifact
    observationReview?: RawObservationReviewArtifact
    simulationReview?: RawSimulationReviewArtifact
    reviewSummary?: RawReviewSummaryArtifact
  }
) => {
  const embeddedReview = hypothesis.review ?? {}
  return {
    initial_review: {
      ...(embeddedReview.initial_review ?? {}),
      ...(reviewArtifacts.initialReview ?? {})
    } satisfies RawInitialReviewArtifact,
    full_review: {
      ...(embeddedReview.full_review ?? {}),
      ...(reviewArtifacts.fullReview ?? {})
    } satisfies RawFullReviewArtifact,
    deep_verification_review: {
      ...(embeddedReview.deep_verification_review ?? {}),
      ...(reviewArtifacts.deepVerificationReview ?? {})
    } satisfies RawDeepVerificationReviewArtifact,
    observation_review: {
      ...(embeddedReview.observation_review ?? {}),
      ...(reviewArtifacts.observationReview ?? {})
    } satisfies RawObservationReviewArtifact,
    simulation_review: {
      ...(embeddedReview.simulation_review ?? {}),
      ...(reviewArtifacts.simulationReview ?? {})
    } satisfies RawSimulationReviewArtifact,
    review_summary: {
      ...(embeddedReview.review_summary ?? {}),
      ...(reviewArtifacts.reviewSummary ?? {})
    } satisfies RawReviewSummaryArtifact
  }
}

const buildReviewBundle = (review: ReturnType<typeof mergeReviewArtifacts>): ReviewBundleRecord => ({
  initial_review: {
    passed: hasCompletedStatus(review.initial_review.status) ? Boolean(review.initial_review.passed) : null,
    summary: buildInitialReviewSummary(review.initial_review)
  },
  full_review: {
    summary: buildFullReviewSummary(review.full_review)
  },
  deep_verification_review: {
    summary: buildDeepVerificationSummary(review.deep_verification_review)
  },
  observation_review: {
    summary: buildObservationSummary(review.observation_review)
  },
  simulation_review: {
    summary: buildSimulationSummary(review.simulation_review)
  }
})

const buildReviewSections = (review: ReturnType<typeof mergeReviewArtifacts>): ReviewSectionRecord[] => {
  const sections: ReviewSectionRecord[] = []

  if (hasCompletedStatus(review.initial_review.status)) {
    sections.push({
      key: 'initial_review',
      title: 'Initial Review',
      verdict: review.initial_review.passed ? 'PASS' : 'FAIL',
      entries: [
        buildReviewEntry('Preferences', toStringList(review.initial_review.preferences)),
        buildReviewEntry('Constraints', toStringList(review.initial_review.constraints))
      ]
    })
  }

  if (hasCompletedStatus(review.full_review.status)) {
    sections.push({
      key: 'full_review',
      title: 'Full Review',
      entries: [
        buildReviewEntry('Preferences', toStringList(review.full_review.preferences)),
        buildReviewEntry('Constraints', toStringList(review.full_review.constraints))
      ]
    })
  }

  if (hasCompletedStatus(review.deep_verification_review.status)) {
    sections.push({
      key: 'deep_verification_review',
      title: 'Deep Verification',
      entries: [
        buildReviewEntry('Assumptions', flattenAssumptions(review.deep_verification_review.assumptions ?? []))
      ]
    })
  }

  if (hasCompletedStatus(review.observation_review.status)) {
    sections.push({
      key: 'observation_review',
      title: 'Observation Review',
      entries: [
        buildReviewEntry(
          'Observations',
          (review.observation_review.observations ?? [])
            .map((observation) => {
              const reasoning = observation.reasoning?.trim()
              return reasoning ? `[${observation.conclusion ?? 'neutral'}] ${reasoning}` : ''
            })
            .filter(Boolean)
        )
      ]
    })
  }

  if (hasCompletedStatus(review.simulation_review.status)) {
    sections.push({
      key: 'simulation_review',
      title: 'Simulation Review',
      entries: [
        buildReviewEntry('Steps', toStringList(review.simulation_review.steps)),
        buildReviewEntry('Failure Scenarios', toStringList(review.simulation_review.failure_scenarios))
      ]
    })
  }

  if (hasCompletedStatus(review.review_summary.status)) {
    sections.push({
      key: 'review_summary',
      title: 'Review Summary',
      entries: [
        buildReviewEntry('Summary', toStringList(review.review_summary.summaries))
      ]
    })
  }

  return sections
}

const isViableHypothesis = (hypothesis: HypothesisRecord) => hypothesis.review.initial_review.passed === true

const describeStopReason = (value: string | undefined) => {
  switch (value) {
    case 'convergence_reached':
      return 'The run stopped because the convergence threshold was reached.'
    case 'max_iterations_reached':
      return 'The run stopped because it hit the user-selected capped iteration limit.'
    case 'safety_iteration_limit_reached':
      return 'The run stopped because it hit the internal safety iteration ceiling.'
    case 'candidate_quality_plateau':
      return 'The run stopped because candidate quality plateaued.'
    case 'no_viable_candidates':
      return 'The run stopped because no viable candidates remained.'
    case 'operator_stop':
      return 'The run stopped because the operator requested a stop.'
    case 'validation_blocked':
      return 'The run stopped because validation blocked further execution.'
    case 'budget_exhausted':
      return 'The run stopped because the configured budget guard was exhausted.'
    case 'manual_override_complete':
      return 'The run stopped because a manual override marked it complete.'
    default:
      return ''
  }
}

const hasInitializedIslandMetrics = (islands: CoScientistState['islands']) =>
  Object.values(islands).some((island) => island.visit_count > 0 || island.decayed_visits > 0 || island.decayed_reward > 0)

const hasConvergenceSignalConflict = (evolutionState?: EvolutionStateArtifact) =>
  evolutionState?.enteredTopKLastRound === true && (evolutionState.convergenceCount ?? 0) > 0

const readLatestSelectionStrategy = (routing: DashboardRoutingArtifacts) => {
  const selectionStrategy = routing.latest_strategy_decision?.signals?.selection_strategy
  return typeof selectionStrategy === 'string' && selectionStrategy ? selectionStrategy : ''
}

const buildIterationStrategySection = (
  routing: DashboardRoutingArtifacts,
  allHypotheses: HypothesisRecord[],
  islands: CoScientistState['islands'],
  evolutionState?: EvolutionStateArtifact,
  completionDecision?: CompletionDecisionArtifact
) => {
  const items: string[] = []
  let badge = 'Pending'

  const policy = routing.policy_decision?.policy
  const convergence = routing.resolved_config?.convergence
  const evolvedHypothesisCount = allHypotheses.filter((hypothesis) => hypothesis.parent_ids.length > 0).length
  const latestSelectionStrategy = readLatestSelectionStrategy(routing)
  const islandMetricsInitialized = hasInitializedIslandMetrics(islands)
  const convergenceSignalConflict = hasConvergenceSignalConflict(evolutionState)

  if (policy) {
    items.push(`Budget profile is \`${policy.budget_profile}\` and controls per-round intensity.`)
    if (policy.iteration_policy === 'capped') {
      const bandLabel = formatIterationBand(policy.iteration_band)
      items.push(
        bandLabel
          ? `Iteration policy is \`capped\` with user-selected band \`${bandLabel}\`.`
          : 'Iteration policy is `capped`.'
      )
    } else {
      items.push(
        'Iteration policy is `completion_driven`, so semantic completion signals decide when the run should stop.'
      )
    }
    items.push(`Stop policy is \`${policy.stop_policy}\`.`)
    badge = 'Configured'
  }

  if (convergence) {
    if (convergence.max_iterations > 0) {
      items.push(
        `Resolved hard cap is \`${convergence.max_iterations}\` iterations from \`${convergence.iteration_cap_source}\`.`
      )
    } else {
      items.push(
        'Resolved hard cap is disabled for the user-facing run; semantic completion is guarded by an internal safety ceiling.'
      )
    }
    items.push(`Safety iteration ceiling is \`${convergence.safety_max_iterations}\`.`)
    badge = 'Configured'
  }

  if (evolutionState) {
    items.push(
      `Current progress is \`${evolutionState.iterationCount ?? 0}\` iterations with convergence \`${evolutionState.convergenceCount ?? 0}/${evolutionState.convergenceThreshold ?? 0}\`.`
    )
    if (latestSelectionStrategy) {
      items.push(`Latest routing mode is \`${latestSelectionStrategy}\`.`)
    }
    if (evolutionState.lastSelectedIsland) {
      items.push(`Last selected island was \`${evolutionState.lastSelectedIsland}\`.`)
    }
    if (evolutionState.lastSelectedStrategy) {
      items.push(`Last concrete evolution strategy was \`${evolutionState.lastSelectedStrategy}\`.`)
    }
    const stopSummary = describeStopReason(evolutionState.stopReason)
    if (stopSummary) {
      items.push(stopSummary)
      badge = 'Stopped'
    } else if (evolutionState.status === 'running') {
      items.push('The run is still active and has not recorded a stop reason yet.')
      badge = 'Running'
    }
  }

  if (completionDecision?.decision && completionDecision.decision !== 'continue_evolution') {
    items.push(`Current completion action is \`${completionDecision.decision}\`.`)
    if (badge === 'Pending') {
      badge = 'Configured'
    }
  }

  if (evolvedHypothesisCount > 0 && !islandMetricsInitialized) {
    items.push(
      `**Warning:** island metrics remain uninitialized even though \`${evolvedHypothesisCount}\` evolved hypotheses exist. UCB selection and stagnation-driven multi-island routing may be unreliable for this run.`
    )
    badge = 'Warning'
  }

  if (convergenceSignalConflict) {
    items.push(
      '**Warning:** convergence signals are inconsistent because `enteredTopKLastRound` is `true` while `convergenceCount` remains above `0`.'
    )
    badge = 'Warning'
  }

  return {
    title: 'Iteration Strategy',
    badge,
    icon: 'brain',
    items: items.length ? items : ['No iteration strategy summary available yet.']
  }
}

const buildArtifactSnapshot = async (runId: string, runDir: string, updatedAt: string, routing: DashboardRoutingArtifacts): Promise<DashboardSnapshot | null> => {
  const [researchPlan, hypotheses, tournament, pipelineState, evolutionState, completionDecision, islandsArtifact] = await Promise.all([
    readJson<RawResearchPlanArtifact>(join(runDir, 'research_plan', 'RESEARCH_PLAN.json')),
    readHypothesisArtifacts(runDir),
    readLatestTournament(runDir),
    readJson<PipelineStateArtifact>(join(runDir, 'state', 'PIPELINE_STATE.json')),
    readJson<EvolutionStateArtifact>(join(runDir, 'state', 'EVOLUTION_STATE.json')),
    readJson<CompletionDecisionArtifact>(join(runDir, 'state', 'COMPLETION_DECISION.json')),
    readJson<RawIslandsArtifact>(join(runDir, 'islands', 'ISLANDS.json'))
  ])

  if (!researchPlan?.research_goal && hypotheses.length === 0) {
    return null
  }

  const orderedHypotheses = [...hypotheses].sort((left, right) => {
    return Date.parse(left.timestamp) - Date.parse(right.timestamp)
  })
  const aliases = new Map(orderedHypotheses.map((hypothesis, index) => [hypothesis.id, `H${String(index + 1).padStart(4, '0')}`]))

  const ratingMap = tournament?.updated_ratings ?? {}
  const hypothesisMap = new Map(hypotheses.map((hypothesis) => [hypothesis.id, hypothesis]))
  const orderedRankingIds = (tournament?.top_k_ids ?? []).filter((hypothesisId) => hypothesisMap.has(hypothesisId))

  for (const hypothesis of hypotheses) {
    hypothesis.alias = aliases.get(hypothesis.id) ?? hypothesis.id
    hypothesis.elo_rating = Math.round(computeElo(hypothesis, ratingMap))
    hypothesis.parent_aliases = hypothesis.parent_ids.map((parentId) => aliases.get(parentId) ?? parentId)
  }

  const syntheticIslandId = hypotheses.some((hypothesis) => hypothesis.island_id) ? '' : 'frontier'
  const hypothesesWithIslands = hypotheses.map((hypothesis) => ({
    ...hypothesis,
    island_id: hypothesis.island_id || syntheticIslandId
  }))
  const islandPayloadById = new Map(
    (Array.isArray(islandsArtifact?.items) ? islandsArtifact.items : [])
      .filter((item): item is RawIslandArtifact => Boolean(item?.id))
      .map((item) => [item.id as string, item])
  )
  const islandIds = [...new Set([
    ...[...islandPayloadById.keys()],
    ...hypothesesWithIslands.map((hypothesis) => hypothesis.island_id).filter(Boolean)
  ])].sort((left, right) => left.localeCompare(right))
  const islandAliases = new Map(islandIds.map((islandId, index) => [islandId, `I${String(index + 1).padStart(3, '0')}`]))

  for (const hypothesis of hypothesesWithIslands) {
    hypothesis.island_alias = islandAliases.get(hypothesis.island_id) ?? ''
  }

  const stateHypotheses = [...hypothesesWithIslands].sort((left, right) => {
    const eloDelta = right.elo_rating - left.elo_rating
    if (eloDelta !== 0) {
      return eloDelta
    }
    return left.timestamp.localeCompare(right.timestamp)
  })
  const hypothesesById = Object.fromEntries(stateHypotheses.map((hypothesis) => [hypothesis.id, hypothesis]))
  const islands = Object.fromEntries(
    islandIds.map((islandId) => [
      islandId,
      {
        id: islandId,
        alias: islandAliases.get(islandId) ?? islandId,
        decayed_reward: toFiniteNumber(islandPayloadById.get(islandId)?.decayed_reward),
        decayed_visits: toFiniteNumber(islandPayloadById.get(islandId)?.decayed_visits),
        visit_count: typeof islandPayloadById.get(islandId)?.visit_count === 'number'
          ? islandPayloadById.get(islandId)!.visit_count as number
          : hypothesesWithIslands.filter((hypothesis) => hypothesis.island_id === islandId).length
      }
    ])
  )
  const displayHypotheses = hypothesesWithIslands
    .filter(isViableHypothesis)
    .sort((left, right) => {
      const eloDelta = right.elo_rating - left.elo_rating
      if (eloDelta !== 0) {
        return eloDelta
      }
      const rankingDelta = orderedRankingIds.indexOf(left.id) - orderedRankingIds.indexOf(right.id)
      if (rankingDelta !== 0 && orderedRankingIds.includes(left.id) && orderedRankingIds.includes(right.id)) {
        return rankingDelta
      }
      return left.timestamp.localeCompare(right.timestamp)
    })

  const ranking = displayHypotheses.map((hypothesis, index) => ({
    id: hypothesis.id,
    rank: index + 1,
    title: `${hypothesis.alias} - ${hypothesis.origin.content.summary || hypothesis.id}`,
    subtitle: hypothesis.origin.content.category || hypothesis.origin.strategy.replaceAll('_', ' '),
    elo: Math.round(hypothesis.elo_rating),
    tone: rankingTones[index % rankingTones.length]
  }))

  const graphSeed = buildGraphSeed(displayHypotheses, islands)

  const insightSections = await readInsightSections(
    runDir,
    displayHypotheses,
    hypothesesWithIslands,
    islands,
    routing,
    evolutionState,
    completionDecision
  )
  const iterationCount = pipelineState?.iterationCount ?? pipelineState?.iteration ?? evolutionState?.iterationCount ?? tournament?.iteration ?? 0
  const convergenceCount = pipelineState?.convergenceCount ?? pipelineState?.convergence_count ?? evolutionState?.convergenceCount ?? 0
  const metrics = [
    { label: 'Hypotheses', value: hypotheses.length, tone: 'blue' as const },
    { label: 'Islands', value: islandIds.length, tone: 'green' as const },
    { label: 'Iterations', value: iterationCount, tone: 'amber' as const },
    { label: 'Convergence', value: convergenceCount, tone: 'violet' as const }
  ]

  return {
    runId,
    updatedAt,
    hasData: true,
    state: {
      research_plan: {
        research_goal: researchPlan?.research_goal ?? '',
        preferences: toStringList(researchPlan?.preferences),
        constraints: toStringList(researchPlan?.constraints)
      },
      hypotheses: hypothesesById,
      islands,
      iteration_count: iterationCount,
      convergence_count: convergenceCount
    },
    metrics,
    ranking,
    graphSeed,
    insightSections,
    routing
  }
}

const buildGraphSeed = (hypotheses: HypothesisRecord[], islands: CoScientistState['islands']) => {
  const syntheticIslandId = hypotheses[0]?.island_id ?? 'frontier'
  const grouped = new Map<string, HypothesisRecord[]>()

  for (const hypothesis of hypotheses) {
    const islandId = hypothesis.island_id || syntheticIslandId
    const islandHypotheses = grouped.get(islandId) ?? []
    islandHypotheses.push(hypothesis)
    grouped.set(islandId, islandHypotheses)
  }

  const graphIslands = Object.values(islands)
    .sort((left, right) => left.alias.localeCompare(right.alias))
    .flatMap((island) => {
      const islandHypotheses = grouped.get(island.id) ?? []
      if (islandHypotheses.length === 0) {
        return []
      }
      return [{
        id: island.id,
        nodes: islandHypotheses.map((hypothesis) => ({
          id: hypothesis.id,
          label: hypothesis.alias,
          score: Math.round(hypothesis.elo_rating)
        })),
        edges: islandHypotheses
          .flatMap((hypothesis) =>
            hypothesis.parent_ids
              .filter((parentId) => islandHypotheses.some((candidate) => candidate.id === parentId))
              .map((parentId) => ({
                id: `${parentId}->${hypothesis.id}`,
                from: parentId,
                to: hypothesis.id
              }))
          ),
        metrics: {
          id: island.id,
          alias: island.alias,
          decayedReward: island.decayed_reward,
          decayedVisits: island.decayed_visits,
          visitCount: island.visit_count
        }
      }]
    })

  const allHypothesisIds = new Set(hypotheses.map((hypothesis) => hypothesis.id))
  const crossEdges = hypotheses.flatMap((hypothesis) =>
    hypothesis.parent_ids
      .filter((parentId) => allHypothesisIds.has(parentId) && !graphIslands.some((island) => island.id === hypothesis.island_id && island.nodes.some((node) => node.id === parentId)))
      .map((parentId) => ({
        id: `${parentId}->${hypothesis.id}`,
        from: parentId,
        to: hypothesis.id
      }))
  )

  return {
    islands: graphIslands,
    crossEdges
  }
}

const readInsightSections = async (
  runDir: string,
  hypotheses: HypothesisRecord[],
  allHypotheses: HypothesisRecord[],
  islands: CoScientistState['islands'],
  routing: DashboardRoutingArtifacts,
  evolutionState?: EvolutionStateArtifact,
  completionDecision?: CompletionDecisionArtifact
) => {
  const [insights, overview] = await Promise.all([
    readJson<{ status?: string, content?: string[] }>(join(runDir, 'meta', 'INSIGHTS_FROM_REVIEWS.json')),
    readJson<{ status?: string, content?: string }>(join(runDir, 'meta', 'RESEARCH_OVERVIEW.json'))
  ])

  const derivedInsightItems = deriveReviewInsightItems(hypotheses)
  const derivedOverviewItems = deriveOverviewItems(hypotheses)

  return [
    {
      title: 'Insights From Reviews',
      badge: insights?.status === 'completed' ? 'Synthesized' : derivedInsightItems.length ? 'Derived' : 'In Review',
      icon: 'message-square',
      items: Array.isArray(insights?.content) && insights.content.length
        ? insights.content
        : derivedInsightItems.length
          ? derivedInsightItems
          : ['No review insights available yet.']
    },
    {
      title: 'Research Overview',
      badge: overview?.status === 'completed' ? 'Complete' : derivedOverviewItems.length ? 'Live' : 'In Review',
      icon: 'book-open',
      items: overview?.content?.trim()
        ? [overview.content]
        : derivedOverviewItems.length
          ? derivedOverviewItems
          : ['No research overview available yet.']
    },
    buildIterationStrategySection(routing, allHypotheses, islands, evolutionState, completionDecision)
  ]
}

const deriveReviewInsightItems = (hypotheses: HypothesisRecord[]) => {
  const seen = new Set<string>()
  const items: string[] = []

  for (const hypothesis of hypotheses) {
    const summarySection = hypothesis.review_sections.find((section) => section.key === 'review_summary')
    if (!summarySection) {
      continue
    }
    for (const entry of summarySection.entries) {
      for (const item of entry.items) {
        const normalized = item.trim()
        if (!normalized || seen.has(normalized)) {
          continue
        }
        seen.add(normalized)
        items.push(normalized)
        if (items.length >= 8) {
          return items
        }
      }
    }
  }

  return items
}

const deriveOverviewItems = (hypotheses: HypothesisRecord[]) => {
  if (hypotheses.length === 0) {
    return []
  }

  const leaders = hypotheses.slice(0, 3)
  const categories = [...new Set(leaders.map((hypothesis) => hypothesis.origin.content.category).filter(Boolean))]
  const items = [
    `Current lead candidate: ${leaders[0]?.origin.content.summary || leaders[0]?.alias || leaders[0]?.id}.`,
    `Active candidate count: ${hypotheses.length}. Top-ranked set: ${leaders.map((hypothesis) => hypothesis.alias).join(', ')}.`
  ]
  if (categories.length > 0) {
    items.push(`Leading categories in the current frontier: ${categories.join(', ')}.`)
  }
  return items
}

const computeElo = (hypothesis: HypothesisRecord, ratingMap: Record<string, RawTournamentRating>) => {
  const tournamentElo = ratingMap[hypothesis.id]?.elo
  if (typeof tournamentElo === 'number' && Number.isFinite(tournamentElo)) {
    return tournamentElo
  }
  if (Number.isFinite(hypothesis.elo_rating)) {
    return hypothesis.elo_rating
  }
  return 1000
}

const readLatestTournament = async (runDir: string): Promise<RawTournamentArtifact | undefined> => {
  const tournamentsDir = join(runDir, 'tournaments')
  try {
    const entries = await readdir(tournamentsDir, { withFileTypes: true })
    const tournaments = await Promise.all(
      entries.map(async (entry) => {
        const path = entry.isDirectory()
          ? join(tournamentsDir, entry.name, 'TOURNAMENT.json')
          : join(tournamentsDir, entry.name)
        return readJson<RawTournamentArtifact>(path)
      })
    )
    return tournaments
      .filter((entry): entry is RawTournamentArtifact => Boolean(entry))
      .sort((left, right) => {
        const iterationDelta = (right.iteration ?? 0) - (left.iteration ?? 0)
        if (iterationDelta !== 0) {
          return iterationDelta
        }
        return Date.parse(right.created_at ?? '') - Date.parse(left.created_at ?? '')
      })[0]
  } catch (error) {
    if (typeof error === 'object' && error && 'code' in error && error.code === 'ENOENT') {
      return undefined
    }
    throw error
  }
}

const readHypothesisArtifacts = async (runDir: string): Promise<HypothesisRecord[]> => {
  const hypothesesDir = join(runDir, 'hypotheses')
  try {
    const entries = await readdir(hypothesesDir, { withFileTypes: true })
    const hypotheses = await Promise.all(
      entries
        .filter((entry) => entry.isDirectory())
        .map(async (entry) => {
          const hypothesisDir = join(hypothesesDir, entry.name)
          const [hypothesis, origin, initialReview, fullReview, deepVerificationReview, observationReview, simulationReview, reviewSummary] = await Promise.all([
            readJson<RawHypothesisArtifact>(join(hypothesisDir, 'HYPOTHESIS.json')),
            readJson<RawOriginArtifact>(join(hypothesisDir, 'ORIGIN.json')),
            readJson<RawInitialReviewArtifact>(join(hypothesisDir, 'REVIEW', 'INITIAL_REVIEW.json')),
            readJson<RawFullReviewArtifact>(join(hypothesisDir, 'REVIEW', 'FULL_REVIEW.json')),
            readJson<RawDeepVerificationReviewArtifact>(join(hypothesisDir, 'REVIEW', 'DEEP_VERIFICATION.json')),
            readJson<RawObservationReviewArtifact>(join(hypothesisDir, 'REVIEW', 'OBSERVATION_REVIEW.json')),
            readJson<RawSimulationReviewArtifact>(join(hypothesisDir, 'REVIEW', 'SIMULATION_REVIEW.json')),
            readJson<RawReviewSummaryArtifact>(join(hypothesisDir, 'REVIEW', 'REVIEW_SUMMARY.json'))
          ])

          if (!hypothesis) {
            return null
          }

          const content = hypothesis.origin?.content ?? hypothesis.content ?? {}
          const parentIds = Array.isArray(hypothesis.parent_ids)
            ? hypothesis.parent_ids
            : hypothesis.parent_id
              ? [hypothesis.parent_id]
              : []
          const hypothesisId = hypothesis.id ?? entry.name
          const review = mergeReviewArtifacts(hypothesis, {
            initialReview,
            fullReview,
            deepVerificationReview,
            observationReview,
            simulationReview,
            reviewSummary
          })

          return {
            id: hypothesisId,
            alias: hypothesisId,
            timestamp: normalizeTimestamp(hypothesis.timestamp ?? hypothesis.created_at, new Date().toISOString()),
            elo_rating: hypothesis.elo_rating ?? 1000,
            origin: {
              strategy: hypothesis.origin?.strategy ?? origin?.strategy ?? hypothesis.evolution_type ?? 'generated',
              content: {
                statement: content.statement ?? '',
                mechanism: content.mechanism ?? '',
                experimental_design: toExperimentalDesign(content.experimental_design),
                summary: content.summary ?? '',
                category: content.category ?? ''
              }
            },
            review: buildReviewBundle(review),
            review_sections: buildReviewSections(review),
            island_id: hypothesis.island_id ?? '',
            island_alias: '',
            parent_ids: parentIds,
            parent_aliases: []
          } satisfies HypothesisRecord
        })
    )
    return hypotheses.filter((hypothesis): hypothesis is HypothesisRecord => Boolean(hypothesis))
  } catch (error) {
    if (typeof error === 'object' && error && 'code' in error && error.code === 'ENOENT') {
      return []
    }
    throw error
  }
}

const ensureRunDir = async (runId: string) => {
  const runDir = join(resolveRunsDir(), runId)
  try {
    const info = await stat(runDir)
    if (!info.isDirectory()) {
      throw createError({ statusCode: 404, statusMessage: `Dashboard run not found: ${runId}` })
    }
  } catch (error) {
    if (typeof error === 'object' && error && 'statusCode' in error) {
      throw error
    }
    if (typeof error === 'object' && error && 'code' in error && error.code === 'ENOENT') {
      throw createError({ statusCode: 404, statusMessage: `Dashboard run not found: ${runId}` })
    }
    throw error
  }
  return runDir
}

const resolveUpdatedAt = async (runDir: string) => {
  const snapshot = await readJson<{ updatedAt?: string }>(join(runDir, 'dashboard', 'SNAPSHOT.json'))
  const currentStage = await readJson<StageArtifact>(join(runDir, 'state', 'CURRENT_STAGE.json'))
  if (snapshot?.updatedAt) {
    return snapshot.updatedAt
  }
  if (currentStage?.updatedAt) {
    return currentStage.updatedAt
  }
  return (await stat(runDir)).mtime.toISOString()
}

export const listDashboardRuns = async (): Promise<RunSummary[]> => {
  const runsDir = resolveRunsDir()
  try {
    const entries = await readdir(runsDir, { withFileTypes: true })
    const summaries = await Promise.all(
      entries
        .filter((entry) => entry.isDirectory() && !entry.name.startsWith('_'))
        .map(async (entry) => {
          const runDir = join(runsDir, entry.name)
          const snapshot = await readJson<DashboardSnapshot>(join(runDir, 'dashboard', 'SNAPSHOT.json'))
          return {
            runId: entry.name,
            updatedAt: await resolveUpdatedAt(runDir),
            hasDatabase: false,
            hasSnapshot: Boolean(snapshot)
          } satisfies RunSummary
        })
    )

    return summaries.sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt))
  } catch (error) {
    if (typeof error === 'object' && error && 'code' in error && error.code === 'ENOENT') {
      return []
    }
    throw error
  }
}

export const readDashboardSnapshot = async (runId: string): Promise<DashboardSnapshot> => {
  const runDir = await ensureRunDir(runId)
  const snapshot = await readJson<DashboardSnapshot>(join(runDir, 'dashboard', 'SNAPSHOT.json'))
  const routing = await readRoutingArtifacts(runDir)
  if (snapshot) {
    return {
      ...snapshot,
      routing: {
        ...emptyRouting(),
        ...(snapshot.routing ?? {}),
        ...routing
      }
    }
  }
  const updatedAt = await resolveUpdatedAt(runDir)
  const artifactSnapshot = await buildArtifactSnapshot(runId, runDir, updatedAt, routing)
  if (artifactSnapshot) {
    return artifactSnapshot
  }
  return {
    ...buildEmptySnapshot(runId, updatedAt),
    routing
  }
}

export const readDashboardProgress = async (runId: string): Promise<RunProgress> => {
  const runDir = await ensureRunDir(runId)
  const [currentStage, pipelineState, strategyPlan] = await Promise.all([
    readJson<StageArtifact>(join(runDir, 'state', 'CURRENT_STAGE.json')),
    readJson<PipelineStateArtifact>(join(runDir, 'state', 'PIPELINE_STATE.json')),
    readJson<StrategyPlanArtifact>(join(runDir, 'state', 'STRATEGY_PLAN.json'))
  ])
  const progress = await inferProgressFromArtifacts(runDir, currentStage, pipelineState, strategyPlan)
  return {
    ...progress,
    runId
  }
}

const readRoutingArtifacts = async (runDir: string): Promise<DashboardRoutingArtifacts> => {
  const policyDecision = await readJson<DashboardRoutingArtifacts['policy_decision']>(join(runDir, 'state', 'POLICY_DECISION.json'))
  const resolvedConfig = await readJson<DashboardRoutingArtifacts['resolved_config']>(join(runDir, 'state', 'RESOLVED_RUN_CONFIG.json'))
  const strategyPlan = await readJson<DashboardRoutingArtifacts['strategy_plan']>(join(runDir, 'state', 'STRATEGY_PLAN.json'))
  const strategyDecisions = await readJsonLines<NonNullable<DashboardRoutingArtifacts['latest_strategy_decision']>>(join(runDir, 'state', 'STRATEGY_DECISIONS.jsonl'))

  return {
    policy_decision: policyDecision ?? null,
    resolved_config: resolvedConfig ?? null,
    strategy_plan: strategyPlan ?? null,
    latest_strategy_decision: strategyDecisions.at(-1) ?? null,
    strategy_decision_count: strategyDecisions.length
  }
}
