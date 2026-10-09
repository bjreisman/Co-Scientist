export const parseCreditBudgetInput = (input: string | number): number | null => {
  // Vue converts v-model values on type="number" inputs to numbers automatically.
  const text = String(input).trim()
  if (!text) return null
  const value = Number(text)
  if (!Number.isFinite(value) || value <= 0 || value > Number.MAX_SAFE_INTEGER) throw new Error('Enter a positive number.')
  return value
}
