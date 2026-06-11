<script setup lang="ts">
import { computed } from 'vue'
import type { InsightSection } from '~/types/coScientist'
import { renderMarkdownToHtml } from '~/utils/renderMarkdown'

const props = defineProps<{ section: InsightSection }>()

const sectionClass = computed(() => {
  switch (props.section.title) {
    case 'Insights From Reviews':
      return 'insights-from-reviews-card'
    case 'Research Overview':
      return 'research-overview-card'
    case 'Iteration Strategy':
      return 'iteration-strategy-card'
    default:
      return ''
  }
})

const renderedItems = computed(() =>
  props.section.items.map((item) => ({
    raw: item,
    html: renderMarkdownToHtml(item)
  }))
)
</script>

<template>
  <div class="glass-card insight-card" :class="sectionClass">
    <div class="insight-header">
      <div class="nav-left">
        <AppIcon :name="section.icon" :size="18" style="color: var(--primary)" />
        <div class="insight-title">{{ section.title }}</div>
      </div>
    </div>
    <div class="insight-content">
      <div
        v-for="item in renderedItems"
        :key="item.raw"
        class="insight-item prose"
      >
        <div class="insight-copy" v-html="item.html"></div>
      </div>
    </div>
  </div>
</template>
