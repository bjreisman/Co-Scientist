import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import type { ModelRouting, ModelSetting } from '../../app/types/modelRouting.ts'

const read = async (path: string): Promise<Record<string, any> | null> => {
  try { return JSON.parse(await readFile(path, 'utf8')) } catch { return null }
}
const setting = (data: any, effortKey = 'reasoningEffort'): ModelSetting | null =>
  data && typeof data.model === 'string' ? {
    model: data.model,
    reasoningEffort: typeof data[effortKey] === 'string' ? data[effortKey] : null
  } : null

export const readModelRouting = async (runDir: string): Promise<ModelRouting> => {
  const snapshot = await read(join(runDir, 'state', 'MODEL_POLICY.json'))
  const policy = snapshot?.policy
  const map = (data: any, key: 'task' | 'skill') => Object.entries(data ?? {}).flatMap(([name, role]) => {
    const requested = setting(policy?.roles?.[String(role)], 'reasoning_effort')
    return requested ? [{ [key]: name, role: String(role), requested }] : []
  })
  const directory = join(runDir, 'state', 'model_dispatches')
  let files: string[] = []
  try { files = (await readdir(directory)).filter(name => /^[a-f0-9-]+\.json$/.test(name)) } catch { /* legacy run */ }
  const records = await Promise.all(files.map(name => read(join(directory, name))))
  // Project only routing metadata; never expose findings paths, session IDs or chat content.
  const dispatches = records.filter((data): data is Record<string, any> => Boolean(data && typeof data.skill === 'string')).map(data => ({
    id: String(data.id ?? ''), skill: data.skill, hypothesisId: String(data.hypothesisId ?? ''),
    route: String(data.route ?? ''), status: String(data.status ?? ''), verification: String(data.verification ?? 'unverified'),
    requested: setting(data.requested),
    observed: Array.isArray(data.observed) ? data.observed.flatMap((value: any) => { const s = setting(value); return s ? [s] : [] }) : [],
    createdAt: String(data.createdAt ?? '')
  })).sort((a, b) => b.createdAt.localeCompare(a.createdAt))
  return { configured: Boolean(policy), enabled: policy?.enabled === true,
    fallback: typeof policy?.fallback === 'string' ? policy.fallback : null,
    tasks: map(policy?.tasks, 'task') as ModelRouting['tasks'],
    overrides: map(policy?.skill_overrides, 'skill') as ModelRouting['overrides'], dispatches }
}
