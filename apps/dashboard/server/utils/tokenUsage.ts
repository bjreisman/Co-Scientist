import { readFile, stat, writeFile, rename, realpath } from 'node:fs/promises'
import { join, resolve, relative, isAbsolute } from 'node:path'
import { randomUUID } from 'node:crypto'
import type { TokenUsage } from '../../app/types/tokenUsage'

export const validateCreditBudget = (value: unknown): number | null => {
  if (value === null) return null
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0 || value > Number.MAX_SAFE_INTEGER) throw new Error('Budget must be a positive number or null.')
  return value as number
}

export const validateCreditSpeed = (value: unknown): 'standard' | 'fast' | 'ultrafast' => {
  if (value !== 'standard' && value !== 'fast' && value !== 'ultrafast') throw new Error('Unknown credit speed.')
  return value
}

const readArtifact = async (path: string): Promise<Record<string, unknown>> => {
  try {
    const data = JSON.parse(await readFile(path, 'utf8'))
    return data && typeof data === 'object' && !Array.isArray(data) ? data : {}
  } catch (error) {
    if (error instanceof SyntaxError || (error as NodeJS.ErrnoException).code === 'ENOENT') return {}
    throw error
  }
}

export const tokenUsageRunDir = async (runsDir: string, runId: string) => {
  if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(runId)) throw new Error('Invalid run id.')
  const runDir = resolve(runsDir, runId)
  if (!(await stat(runDir)).isDirectory()) throw new Error('Run directory does not exist.')
  const canonical = await realpath(runDir)
  const offset = relative(await realpath(runsDir), canonical)
  if (!offset || offset.startsWith('..') || isAbsolute(offset)) throw new Error('Run escapes the run root.')
  return canonical
}

export const readTokenUsage = async (runDir: string): Promise<TokenUsage> => {
  const [data, budget] = await Promise.all([
    readArtifact(join(runDir, 'state', 'TOKEN_USAGE.json')),
    readArtifact(join(runDir, 'state', 'CREDIT_BUDGET.json'))
  ])
  const count = (key: string): number | null => Number.isSafeInteger(data[key]) && Number(data[key]) >= 0 ? Number(data[key]) : null
  const text = (key: string): string | null => typeof data[key] === 'string' ? data[key] as string : null
  const input = count('inputTokens')
  const output = count('outputTokens')
  const cached = count('cachedInputTokens')
  const valid = input !== null && output !== null && cached !== null && cached + (count('cacheWriteInputTokens') ?? 0) <= input
    && count('totalTokens') === input + output && count('uncachedInputTokens') === input - cached - (count('cacheWriteInputTokens') ?? 0)
  const available = valid && (data.status === 'available' || data.status === 'partial')
  let budgetCredits: number | null = null
  try { budgetCredits = validateCreditBudget(budget.budgetCredits ?? null) } catch { /* Invalid budgets are unset. */ }
  return {
    status: available ? data.status as 'available' | 'partial' : 'unavailable',
    totalTokens: available ? count('totalTokens') : null,
    inputTokens: available ? input : null,
    cachedInputTokens: available ? cached : null,
    uncachedInputTokens: available ? count('uncachedInputTokens') : null,
    outputTokens: available ? output : null,
    reasoningOutputTokens: available ? count('reasoningOutputTokens') : null,
    cacheWriteInputTokens: available ? count('cacheWriteInputTokens') ?? 0 : null,
    estimatedCredits: available && typeof data.estimatedCredits === 'number' && Number.isFinite(data.estimatedCredits) && data.estimatedCredits >= 0 && ['available', 'partial'].includes(String(data.creditStatus)) ? data.estimatedCredits : null,
    creditStatus: available && ['available', 'partial'].includes(String(data.creditStatus)) ? data.creditStatus as 'available' | 'partial' : 'unavailable',
    unpricedTokens: count('unpricedTokens') ?? 0,
    freeSafetyTokens: count('freeSafetyTokens') ?? 0,
    assumedSpeedTokens: count('assumedSpeedTokens') ?? 0,
    fallbackSpeed: ['standard', 'fast', 'ultrafast'].includes(String(budget.fallbackSpeed)) ? budget.fallbackSpeed as 'standard' | 'fast' | 'ultrafast' : 'standard',
    rateCardDate: text('rateCardDate'),
    modelCredits: Array.isArray(data.modelCredits) ? data.modelCredits.filter((item: any) => item && typeof item.model === 'string' && typeof item.credits === 'number' && Number.isFinite(item.credits) && item.credits >= 0).map((item: any) => ({ model: item.model, credits: item.credits })) : [],
    budgetCredits,
    updatedAt: text('updatedAt'),
    lastUsageAt: text('lastUsageAt'),
    startedAt: text('startedAt'),
    sessionCount: count('sessionCount') ?? 0,
    missingSessionCount: count('missingSessionCount') ?? 0
  }
}

export const writeCreditBudget = async (runDir: string, budgetCredits: unknown, fallbackSpeed: unknown = 'standard') => {
  const value = validateCreditBudget(budgetCredits)
  const path = join(runDir, 'state', 'CREDIT_BUDGET.json')
  const temporary = `${path}.${randomUUID()}.tmp`
  await writeFile(temporary, JSON.stringify({ budgetCredits: value, fallbackSpeed: validateCreditSpeed(fallbackSpeed) }, null, 2) + '\n', 'utf8')
  await rename(temporary, path)
}
