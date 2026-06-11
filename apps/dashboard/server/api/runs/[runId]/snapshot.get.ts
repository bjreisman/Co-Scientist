import { readDashboardSnapshot } from '../../../utils/dashboardArtifacts'

export default defineEventHandler(async (event) => {
  const runId = getRouterParam(event, 'runId')
  if (!runId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing run id.' })
  }
  return readDashboardSnapshot(runId)
})
