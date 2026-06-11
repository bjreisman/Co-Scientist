export interface DashboardClientConfig {
  pollIntervalMs: number
  progressPollIntervalMs: number
  defaultRunId: string
}

const RUNS_ROOT_PATH = 'runs'

export const dashboardClientConfig: DashboardClientConfig = {
  pollIntervalMs: 10_000,
  progressPollIntervalMs: 1_000,
  defaultRunId: 'test1'
}

export const buildRunPath = (runId: string) => {
  const normalizedRoot = RUNS_ROOT_PATH.replace(/[\\/]+$/, '')
  return runId ? `${normalizedRoot}/${runId}` : normalizedRoot
}
