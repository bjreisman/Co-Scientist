<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    message: string
    tone?: 'default' | 'error'
    fullWidth?: boolean
  }>(),
  {
    tone: 'default',
    fullWidth: false
  }
)
</script>

<template>
  <div class="glass-card status-card" :class="{ error: tone === 'error', 'full-width': fullWidth }">
    <div class="status-card-title">{{ title }}</div>
    <p class="status-card-copy">{{ message }}</p>
  </div>
</template>
