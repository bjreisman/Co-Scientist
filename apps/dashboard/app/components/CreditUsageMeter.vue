<script setup lang="ts">
import type { TokenUsage } from '~/types/tokenUsage'
import { parseCreditBudgetInput } from '~/utils/creditBudget'

const props = defineProps<{ usage: TokenUsage | null; enabled: boolean; saving: boolean; error: string | null }>()
const emit = defineEmits<{ (event: 'set-budget', value: number | null, fallbackSpeed: string): void }>()
const editing = ref(false)
const budgetInput = ref<string | number>('')
const speedInput = ref('standard')
const inputError = ref<string | null>(null)
const hasUsage = computed(() => props.usage?.estimatedCredits !== null && props.usage?.estimatedCredits !== undefined)
const budget = computed(() => props.usage?.budgetCredits ?? null)
const percentage = computed(() => hasUsage.value && budget.value ? (props.usage!.estimatedCredits! / budget.value) * 100 : null)
const tone = computed(() => (percentage.value ?? 0) >= 100 ? 'exceeded' : (percentage.value ?? 0) >= 80 ? 'warning' : 'normal')
const stale = computed(() => Boolean(props.usage?.updatedAt) && Date.now() - Date.parse(props.usage!.updatedAt!) > 30000)
const format = (value: number | null | undefined) => value === null || value === undefined ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: 3 })
const edit = () => { budgetInput.value = budget.value?.toString() ?? ''; speedInput.value = props.usage?.fallbackSpeed ?? 'standard'; inputError.value = null; editing.value = !editing.value }
const submit = () => {
  inputError.value = null
  try { emit('set-budget', parseCreditBudgetInput(budgetInput.value), speedInput.value) } catch {
    inputError.value = 'Enter a positive number, or leave blank to remove the budget.'
  }
}
watch(() => props.saving, (saving, previous) => { if (previous && !saving && !props.error) editing.value = false })
</script>

<template>
  <section class="token-meter" :class="tone" aria-label="Run credit usage">
    <div class="token-meter-heading">
      <div>
        <strong>Estimated credits</strong>
        <span v-if="hasUsage" class="token-meter-total">{{ format(usage?.estimatedCredits) }}<span v-if="budget"> / {{ format(budget) }}</span></span>
        <span v-else class="token-meter-muted">{{ enabled ? 'Usage unavailable' : 'Select a run' }}</span>
        <span v-if="percentage !== null" class="token-meter-muted">{{ percentage.toFixed(1) }}%</span>
        <span v-if="usage?.status === 'partial' || usage?.creditStatus === 'partial'" class="token-meter-notice">Partial coverage</span>
        <span v-if="stale" class="token-meter-notice">Tracker needs refreshing</span>
      </div>
      <button type="button" class="token-budget-button" :disabled="!enabled || saving" @click="edit">{{ budget ? 'Edit budget' : 'Set budget' }}</button>
    </div>
    <div v-if="budget && hasUsage" class="token-meter-track" role="progressbar" aria-label="Credit budget used"
      :aria-valuenow="Math.min(percentage ?? 0, 100)" :aria-valuemin="0" :aria-valuemax="100"
      :aria-valuetext="`${format(usage?.estimatedCredits)} of ${format(budget)} credits used`">
      <div class="token-meter-fill" :style="{ width: `${Math.min(percentage ?? 0, 100)}%` }" />
    </div>
    <div class="token-meter-details">
      <template v-if="usage?.totalTokens !== null && usage?.totalTokens !== undefined">
        <span>Input {{ format(usage?.inputTokens) }} · cached {{ format(usage?.cachedInputTokens) }} · uncached {{ format(usage?.uncachedInputTokens) }}</span>
        <span>Output {{ format(usage?.outputTokens) }} · {{ usage?.sessionCount }} tracked sessions</span>
        <span v-if="usage?.unpricedTokens" class="token-meter-notice">{{ format(usage.unpricedTokens) }} tokens unpriced (unknown model/speed)</span>
        <span v-if="usage?.freeSafetyTokens">Safety checks excluded</span>
      </template>
      <span v-else>Waiting for priced Codex usage.</span>
      <span v-if="!budget">No credit budget set.</span>
      <span v-if="tone === 'warning'">Approaching budget.</span>
      <span v-if="tone === 'exceeded'" role="status">Budget exceeded.</span>
      <span>Advisory budget · EDU estimate · {{ usage?.fallbackSpeed ?? 'standard' }} when speed is unreported</span>
    </div>
    <details v-if="usage?.modelCredits.length" class="token-meter-details">
      <summary>Model breakdown · rate card {{ usage?.rateCardDate }}</summary>
      <span v-for="item in usage?.modelCredits" :key="item.model">{{ item.model }}: {{ format(item.credits) }} credits · </span>
      <a href="https://help.openai.com/en/articles/11481834-chatgpt-rate-card-business-enterpriseedu-credit-based-pricing" target="_blank" rel="noopener noreferrer">EDU rate card</a>
    </details>
    <form v-if="editing" class="token-budget-form" @submit.prevent="submit">
      <label for="token-budget">Run budget (credits)</label>
      <input id="token-budget" v-model="budgetInput" type="number" min="0.01" step="any" placeholder="Leave blank to remove budget" :disabled="saving" />
      <label for="credit-speed">Speed when unreported</label>
      <select id="credit-speed" v-model="speedInput" :disabled="saving">
        <option value="standard">Standard (1×)</option><option value="fast">Fast (2×)</option><option value="ultrafast">Ultrafast (6×)</option>
      </select>
      <button type="submit" class="token-budget-button" :disabled="saving">{{ saving ? 'Saving…' : 'Save' }}</button>
      <button type="button" class="token-budget-button" :disabled="saving" @click="editing = false">Cancel</button>
      <span v-if="error || inputError" role="alert">{{ error || inputError }}</span>
    </form>
  </section>
</template>
