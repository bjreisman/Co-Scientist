import { resolveRunsDir } from '../../../utils/dashboardArtifacts'
import { readTokenUsage, tokenUsageRunDir } from '../../../utils/tokenUsage'

export default defineEventHandler(async (event) => {
  const runId = getRouterParam(event, 'runId') ?? ''
  let runDir: string
  try { runDir = await tokenUsageRunDir(resolveRunsDir(), runId) } catch {
    throw createError({ statusCode: 404, statusMessage: 'Run not found.' })
  }
  return readTokenUsage(runDir)
})
