<script setup lang="ts">
import type { MetricItem } from '~/types/coScientist'

defineProps<{ metric: MetricItem }>()

const toneClass = (tone: MetricItem['tone']) => {
  return {
    blue: 'tone-blue',
    green: 'tone-green',
    amber: 'tone-amber',
    violet: 'tone-violet'
  }[tone]
}
</script>

<template>
  <div class="metric-pill" :class="toneClass(metric.tone)">
    {{ metric.label }} {{ metric.value }}
  </div>
</template>
