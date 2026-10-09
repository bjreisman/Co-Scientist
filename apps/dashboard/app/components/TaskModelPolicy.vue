<script setup lang="ts">
import type { ModelRouting, ModelSetting } from '~/types/modelRouting'

const props = defineProps<{ runId?: string }>()
const data = ref<ModelRouting | null>(null)
const error = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
let request = 0
const load = async () => {
  const id = ++request
  if (!props.runId) { data.value = null; error.value = false; return }
  try {
    const result = await $fetch<ModelRouting>(`/api/runs/${encodeURIComponent(props.runId)}/models`)
    if (id === request) { data.value = result; error.value = false }
  } catch { if (id === request) { data.value = null; error.value = true } }
}
onMounted(() => { load(); timer = setInterval(load, 5000) })
onBeforeUnmount(() => { clearInterval(timer); ++request })
watch(() => props.runId, () => { data.value = null; load() })
const label = (value: ModelSetting | null) => value ? `${value.model} · ${value.reasoningEffort ?? 'effort unknown'}` : 'Host settings'
const title = (task: string) => task.replaceAll('_', ' ').replace(/^./, s => s.toUpperCase())
</script>

<template>
  <details v-if="props.runId" class="task-models">
    <summary>Task models <span>{{ error ? 'Unavailable' : data?.configured ? 'Configured' : 'No policy captured' }}</span></summary>
    <div class="task-model-content">
      <p v-if="error">Model routing could not be loaded.</p>
      <p v-else-if="!data?.configured">This run has no saved task model policy. Its tasks use the host settings; historical settings have not been inferred.</p>
      <template v-else>
        <p>Requested settings for this run. {{ data.enabled ? 'Scientific tasks use delegated roles.' : 'Delegation is disabled; host settings apply.' }} Unavailable-agent fallback: {{ data.fallback }}.</p>
        <div class="model-table"><table>
          <thead><tr><th>Task</th><th>Role</th><th>Requested model · reasoning</th></tr></thead>
          <tbody><tr v-for="task in data.tasks" :key="task.task"><td>{{ title(task.task) }}</td><td>{{ task.role }}</td><td>{{ label(task.requested) }}</td></tr>
            <tr v-for="override in data.overrides" :key="override.skill"><td>{{ override.skill }} (override)</td><td>{{ override.role }}</td><td>{{ label(override.requested) }}</td></tr></tbody>
        </table></div>
      </template>
      <template v-if="data?.dispatches.length">
        <h3>Recent dispatches</h3>
        <div class="model-table"><table>
          <thead><tr><th>Task</th><th>Requested</th><th>Observed</th><th>Audit / status</th></tr></thead>
          <tbody><tr v-for="dispatch in data.dispatches.slice(0, 10)" :key="dispatch.id">
            <td>{{ dispatch.skill }} {{ dispatch.hypothesisId }}<small>{{ dispatch.route === 'local_main_thread' ? 'Local review / host settings' : 'Delegated' }}</small></td>
            <td>{{ label(dispatch.requested) }}</td><td>{{ dispatch.observed.length ? dispatch.observed.map(label).join('; ') : 'Not verified' }}</td>
            <td :class="{ mismatch: dispatch.verification === 'mismatch' }">{{ dispatch.verification }} / {{ dispatch.status }}</td>
          </tr></tbody>
        </table></div>
      </template>
      <p v-else-if="data?.configured">No model dispatches recorded yet. Requested settings do not establish actual model use.</p>
    </div>
  </details>
</template>

<style scoped>
.task-models { margin: 0 24px 10px; font-size: 12px; color: var(--muted-foreground); }
summary { cursor: pointer; width: fit-content; padding: 4px 0; color: var(--foreground); }
summary span { margin-left: 8px; color: var(--muted-foreground); }
.task-model-content { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; }
.model-table { overflow-x: auto; } table { width: 100%; border-collapse: collapse; text-align: left; }
th, td { padding: 7px 12px; border-bottom: 1px solid var(--border); } th { color: var(--foreground); }
small { display: block; font-size: 11px; } .mismatch { color: #b91c1c; } h3 { font-size: 13px; }
</style>
