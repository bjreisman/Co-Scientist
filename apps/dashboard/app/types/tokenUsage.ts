export interface TokenUsage {
  status: 'available' | 'partial' | 'unavailable'
  totalTokens: number | null
  inputTokens: number | null
  cachedInputTokens: number | null
  uncachedInputTokens: number | null
  outputTokens: number | null
  reasoningOutputTokens: number | null
  budgetCredits: number | null
  estimatedCredits: number | null
  creditStatus: 'available' | 'partial' | 'unavailable'
  cacheWriteInputTokens: number | null
  unpricedTokens: number
  freeSafetyTokens: number
  assumedSpeedTokens: number
  fallbackSpeed: 'standard' | 'fast' | 'ultrafast'
  rateCardDate: string | null
  modelCredits: { model: string; credits: number }[]
  updatedAt: string | null
  lastUsageAt: string | null
  startedAt: string | null
  sessionCount: number
  missingSessionCount: number
}
