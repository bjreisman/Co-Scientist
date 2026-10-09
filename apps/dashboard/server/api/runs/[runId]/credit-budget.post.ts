import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { resolveRunsDir } from '../../../utils/dashboardArtifacts'
import { readTokenUsage, tokenUsageRunDir, validateCreditBudget, validateCreditSpeed, writeCreditBudget } from '../../../utils/tokenUsage'

export default defineEventHandler(async (event) => {
  const origin = getHeader(event, 'origin')
  if (origin && origin !== getRequestURL(event).origin) {
    throw createError({ statusCode: 403, statusMessage: 'Cross-origin budget changes are not allowed.' })
  }
  if (!getHeader(event, 'content-type')?.startsWith('application/json')) {
    throw createError({ statusCode: 415, statusMessage: 'Use application/json.' })
  }
  let runDir: string
  try { runDir = await tokenUsageRunDir(resolveRunsDir(), getRouterParam(event, 'runId') ?? '') } catch {
    throw createError({ statusCode: 404, statusMessage: 'Run not found.' })
  }
  const body = await readBody(event)
  try { validateCreditBudget(body?.budgetCredits); validateCreditSpeed(body?.fallbackSpeed ?? 'standard') } catch {
    throw createError({ statusCode: 400, statusMessage: 'Budget must be a positive number or null.' })
  }
  await mkdir(join(runDir, 'state'), { recursive: true })
  await writeCreditBudget(runDir, body.budgetCredits, body.fallbackSpeed ?? 'standard')
  return readTokenUsage(runDir)
})
