<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'

const route = useRoute()
const { metrics, runId } = useDashboardState()
const theme = useState<'light' | 'dark'>('theme', () => 'light')

const activeNav = computed(() => (route.meta.nav as string) ?? 'ranking')

const setTheme = (value: 'light' | 'dark') => {
  theme.value = value
}

useHead(() => ({
  htmlAttrs: {
    'data-theme': theme.value
  }
}))

onMounted(() => {
  const stored = window.localStorage.getItem('theme')
  if (stored === 'light' || stored === 'dark') {
    theme.value = stored
  }
  document.documentElement.setAttribute('data-theme', theme.value)
})

watch(theme, (value) => {
  if (process.client) {
    document.documentElement.setAttribute('data-theme', value)
    window.localStorage.setItem('theme', value)
  }
})
</script>

<template>
  <div class="page-frame">
    <div class="app-shell">
      <div class="main-area">
        <AppTopBar
          :metrics="metrics"
          :current-run-id="runId"
          :theme="theme"
          :active-nav="activeNav"
          @set-theme="setTheme"
        />
        <div class="main-content">
          <slot />
        </div>
      </div>
    </div>
  </div>
</template>
