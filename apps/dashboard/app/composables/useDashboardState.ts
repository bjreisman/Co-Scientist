import { computed, onMounted, onServerPrefetch, readonly, watch } from 'vue'
import type {
  CoScientistState,
  DashboardRoutingArtifacts,
  DashboardSnapshot,
  GraphSeed,
  InsightSection,
  MetricItem,
  PipelineStage,
  RankingItem,
  RunProgress,
  RunSummary
} from '~/types/coScientist'
import { buildRunPath, dashboardClientConfig } from '~/config/dashboard'
import type { TokenUsage } from '~/types/tokenUsage'

let pollTimer: ReturnType<typeof setInterval> | null = null
let progressTimer: ReturnType<typeof setInterval> | null = null
let inFlightLoad: Promise<void> | null = null

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

const emptySnapshot = (): DashboardSnapshot => ({
  runId: '',
  updatedAt: '',
  hasData: false,
  state: emptyState(),
  metrics: [],
  ranking: [],
  graphSeed: {
    islands: [],
    crossEdges: []
  },
  insightSections: [],
  routing: {
    policy_decision: null,
    resolved_config: null,
    strategy_plan: null,
    latest_strategy_decision: null,
    strategy_decision_count: 0
  }
})

const emptyProgress = (): RunProgress => ({
  runId: '',
  currentStage: 'Idle',
  stageTrail: [],
  completedStages: [],
  plannedNextStage: null,
  currentSkill: '',
  source: 'artifact_inference',
  confidence: 'low'
})

const normalizeApiBase = (value: string) => value.replace(/\/+$/, '')

export const useDashboardState = () => {
  const route = useRoute()
  const config = useRuntimeConfig()

  const snapshot = useState<DashboardSnapshot>('dashboard-snapshot', emptySnapshot)
  const runs = useState<RunSummary[]>('dashboard-runs', () => [])
  const pending = useState<boolean>('dashboard-pending', () => false)
  const error = useState<string | null>('dashboard-error', () => null)
  const activeRunId = useState<string>('dashboard-active-run-id', () => '')
  const progress = useState<RunProgress>('dashboard-progress', emptyProgress)
  const tokenUsage = useState<TokenUsage | null>('dashboard-token-usage', () => null)
  const budgetSaving = useState<boolean>('dashboard-budget-saving', () => false)
  const budgetError = useState<string | null>('dashboard-budget-error', () => null)

  const requestedRunId = computed(() => {
    const value = route.query.run
    return typeof value === 'string' ? value : ''
  })

  const apiBase = computed(() => {
    const configuredBase = normalizeApiBase(String(config.public.apiBase ?? ''))
    if (configuredBase) {
      return configuredBase
    }
    if (process.client) {
      return normalizeApiBase(window.location.origin)
    }
    return ''
  })

  const chooseRunId = () => {
    const availableIds = new Set(runs.value.map((run) => run.runId))
    const candidates = [requestedRunId.value, dashboardClientConfig.defaultRunId, runs.value[0]?.runId].filter(
      Boolean
    ) as string[]
    return candidates.find((candidate) => availableIds.has(candidate)) ?? ''
  }

  const refreshProgress = async () => {
    const runId = activeRunId.value
    if (!runId) {
      progress.value = emptyProgress()
      tokenUsage.value = null
      return
    }
    try {
      const nextProgress = await $fetch<RunProgress>(`${apiBase.value}/api/runs/${encodeURIComponent(runId)}/progress`)
      progress.value = {
        runId: nextProgress.runId ?? runId,
        currentStage: nextProgress.currentStage ?? 'Idle',
        stageTrail: nextProgress.stageTrail ?? [],
        completedStages: nextProgress.completedStages ?? [],
        plannedNextStage: nextProgress.plannedNextStage ?? null,
        currentSkill: nextProgress.currentSkill ?? '',
        source: nextProgress.source ?? 'artifact_inference',
        confidence: nextProgress.confidence ?? 'low'
      }
    } catch {
      if (progress.value.runId !== runId) {
        progress.value = {
          runId,
          currentStage: 'Idle',
          stageTrail: [],
          completedStages: [],
          plannedNextStage: null,
          currentSkill: '',
          source: 'artifact_inference',
          confidence: 'low'
        }
      }
    }
    try {
      const usage = await $fetch<TokenUsage>(`${apiBase.value}/api/runs/${encodeURIComponent(runId)}/usage`)
      if (activeRunId.value === runId) tokenUsage.value = usage
    } catch {
      if (activeRunId.value === runId) tokenUsage.value = null
    }
  }

  const setCreditBudget = async (budgetCredits: number | null, fallbackSpeed: string = 'standard') => {
    const runId = activeRunId.value
    if (!runId || budgetSaving.value) return
    budgetSaving.value = true
    budgetError.value = null
    try {
      const usage = await $fetch<TokenUsage>(`${apiBase.value}/api/runs/${encodeURIComponent(runId)}/credit-budget`, {
        method: 'POST', body: { budgetCredits, fallbackSpeed }
      })
      if (activeRunId.value === runId) tokenUsage.value = usage
    } catch {
      budgetError.value = 'Could not save the credit budget. Please try again.'
    } finally {
      budgetSaving.value = false
    }
  }

  watch(activeRunId, () => { tokenUsage.value = null; budgetError.value = null })

  const refresh = async (force = false) => {
    if (inFlightLoad) {
      return inFlightLoad
    }

    const load = async () => {
      const shouldShowPending = force || !snapshot.value.hasData
      if (shouldShowPending) {
        pending.value = true
      }
      try {
        const runList = await $fetch<RunSummary[]>(`${apiBase.value}/api/runs`)
        runs.value = runList

        const resolvedRunId = chooseRunId()
        activeRunId.value = resolvedRunId

        if (!resolvedRunId) {
          snapshot.value = emptySnapshot()
          progress.value = emptyProgress()
          tokenUsage.value = null
          error.value = null
          return
        }

        const nextSnapshot = await $fetch<DashboardSnapshot>(
          `${apiBase.value}/api/runs/${encodeURIComponent(resolvedRunId)}/snapshot`
        )
        snapshot.value = nextSnapshot
        await refreshProgress()
        error.value = null
      } catch (cause) {
        error.value = cause instanceof Error ? cause.message : 'Failed to load dashboard snapshot.'
      } finally {
        pending.value = false
      }
    }

    inFlightLoad = load().finally(() => {
      inFlightLoad = null
    })
    return inFlightLoad
  }

  onServerPrefetch(() => refresh())

  if (!pending.value && !snapshot.value.hasData && !process.server) {
    void refresh()
  }

  watch(
    requestedRunId,
    () => {
      void refresh(true)
    }
  )

  onMounted(() => {
    if (!pollTimer) {
      pollTimer = window.setInterval(() => {
        void refresh(true)
      }, dashboardClientConfig.pollIntervalMs)
    }
    if (!progressTimer) {
      progressTimer = window.setInterval(() => {
        void refreshProgress()
      }, dashboardClientConfig.progressPollIntervalMs)
    }
  })

  const graphSeed = computed<GraphSeed>(() => snapshot.value.graphSeed)
  const currentStage = computed<PipelineStage>(() => progress.value.currentStage)
  const stageTrail = computed<PipelineStage[]>(() => progress.value.stageTrail)
  const completedStages = computed<PipelineStage[]>(() => progress.value.completedStages)
  const plannedNextStage = computed<PipelineStage | null>(() => progress.value.plannedNextStage ?? null)
  const currentSkill = computed<string>(() => progress.value.currentSkill)
  const progressSource = computed<RunProgress['source']>(() => progress.value.source)
  const progressConfidence = computed<RunProgress['confidence']>(() => progress.value.confidence)
  const hasData = computed(() => snapshot.value.hasData)
  const runPath = computed(() => buildRunPath(activeRunId.value))
  const state = computed(() => snapshot.value.state)
  const metrics = computed<MetricItem[]>(() => snapshot.value.metrics)
  const ranking = computed<RankingItem[]>(() => snapshot.value.ranking)
  const insightSections = computed<InsightSection[]>(() => snapshot.value.insightSections)
  const routing = computed<DashboardRoutingArtifacts>(() => snapshot.value.routing)

  return {
    runs: readonly(runs),
    runId: readonly(activeRunId),
    runPath,
    state,
    metrics,
    tokenUsage: readonly(tokenUsage),
    budgetSaving: readonly(budgetSaving),
    budgetError: readonly(budgetError),
    setCreditBudget,
    ranking,
    graphSeed,
    insightSections,
    routing,
    currentStage,
    stageTrail,
    completedStages,
    plannedNextStage,
    currentSkill,
    progressSource,
    progressConfidence,
    pending: readonly(pending),
    error: readonly(error),
    hasData,
    refresh: () => refresh(true)
  }
}
