import { resolveRunsDir } from '../../../utils/dashboardArtifacts'
import { tokenUsageRunDir } from '../../../utils/tokenUsage'
import { readModelRouting } from '../../../utils/modelRouting'

export default defineEventHandler(async event => {
  let runDir: string
  try { runDir = await tokenUsageRunDir(resolveRunsDir(), getRouterParam(event, 'runId') ?? '') } catch {
    throw createError({ statusCode: 404, statusMessage: 'Run not found.' })
  }
  return readModelRouting(runDir)
})
