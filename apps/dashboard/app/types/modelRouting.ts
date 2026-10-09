export type ModelSetting = { model: string; reasoningEffort: string | null }
export type ModelRouting = {
  configured: boolean
  enabled: boolean
  fallback: string | null
  tasks: { task: string; role: string; requested: ModelSetting }[]
  overrides: { skill: string; role: string; requested: ModelSetting }[]
  dispatches: {
    id: string; skill: string; hypothesisId: string; route: string; status: string
    verification: string; requested: ModelSetting | null; observed: ModelSetting[]
    createdAt: string
  }[]
}
