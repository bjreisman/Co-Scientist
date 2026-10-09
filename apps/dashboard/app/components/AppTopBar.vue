<script setup lang="ts">
import type { MetricItem } from '~/types/coScientist'
import type { TokenUsage } from '~/types/tokenUsage'
import type { LocationQueryRaw, RouteLocationRaw } from 'vue-router'

const route = useRoute()

const props = withDefaults(
  defineProps<{
    metrics: MetricItem[]
    activeNav: string
    currentRunId?: string
    theme?: 'light' | 'dark'
    tokenUsage: TokenUsage | null
    budgetSaving: boolean
    budgetError: string | null
  }>(),
  {
    theme: 'light'
  }
)

const emit = defineEmits<{
  (event: 'set-theme', value: 'light' | 'dark'): void
  (event: 'set-budget', value: number | null, fallbackSpeed: string): void
}>()

const setTheme = (value: 'light' | 'dark') => {
  emit('set-theme', value)
}

const runQuery = computed<LocationQueryRaw>(() => {
  const query: LocationQueryRaw = { ...route.query }
  const activeRun = props.currentRunId ?? ''
  if (activeRun) {
    query.run = activeRun
  }
  return query
})

const buildNavTarget = (path: string): RouteLocationRaw => ({
  path,
  query: runQuery.value
})

const navItems = computed(() => [
  { key: 'ranking', label: 'Ranking', icon: 'trophy', to: buildNavTarget('/ranking') },
  { key: 'evolution', label: 'Evolution Graph', icon: 'git-branch', to: buildNavTarget('/evolution') },
  { key: 'meta', label: 'Meta-Reviews', icon: 'file-text', to: buildNavTarget('/meta-reviews') }
])
</script>

<template>
  <header class="topbar-shell">
    <div class="topbar">
      <div class="topbar-left">
        <NuxtLink :to="buildNavTarget('/ranking')" class="brand topbar-brand">
          <div class="brand-logo">
            <AppIcon name="brain" :size="16" />
          </div>
          <div class="brand-name">
            <div class="brand-title">Co-Scientist</div>
            <div class="brand-subtitle">Hypothesis Explorer</div>
          </div>
        </NuxtLink>

        <nav class="topbar-nav-inline" aria-label="Dashboard navigation">
          <NuxtLink
            v-for="item in navItems"
            :key="item.key"
            :to="item.to"
            class="topbar-nav-link"
            :class="{ active: props.activeNav === item.key }"
          >
            <AppIcon :name="item.icon" :size="16" />
            <span>{{ item.label }}</span>
          </NuxtLink>
        </nav>
      </div>

      <div class="topbar-right">
        <div class="metric-row">
          <MetricPill v-for="metric in props.metrics" :key="metric.label" :metric="metric" />
        </div>
        <div class="mode-toggle">
          <button
            class="mode-btn"
            :class="{ active: props.theme === 'light' }"
            type="button"
            aria-label="Light mode"
            :aria-pressed="props.theme === 'light'"
            @click="setTheme('light')"
          >
            <AppIcon name="sun" :size="16" />
          </button>
          <button
            class="mode-btn"
            :class="{ active: props.theme === 'dark' }"
            type="button"
            aria-label="Dark mode"
            :aria-pressed="props.theme === 'dark'"
            @click="setTheme('dark')"
          >
            <AppIcon name="moon" :size="16" />
          </button>
        </div>
      </div>
    </div>
    <CreditUsageMeter :usage="props.tokenUsage" :enabled="Boolean(props.currentRunId)"
      :saving="props.budgetSaving" :error="props.budgetError" @set-budget="(budget, speed) => emit('set-budget', budget, speed)" />
    <TaskModelPolicy :run-id="props.currentRunId" />
  </header>
</template>
