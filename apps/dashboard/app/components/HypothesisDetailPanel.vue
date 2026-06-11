<script setup lang="ts">
import { computed } from 'vue'
import type { Hypothesis } from '~/types/coScientist'

const props = defineProps<{
  hypothesis: Hypothesis
  rank: number | null
  displayTitle: string
  panelHeight?: number | null
}>()

const strategyLabel = (strategy: string) => {
  return strategy
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

const parentSummary = computed(() => {
  return props.hypothesis.parent_aliases.length > 0 ? props.hypothesis.parent_aliases.join(', ') : 'None'
})

const islandSummary = computed(() => props.hypothesis.island_alias || 'None')

const rankLabel = computed(() => (props.rank !== null ? `#${props.rank}` : 'Unranked'))

const experimentalDesignSteps = computed(() => {
  const raw = props.hypothesis.origin.content.experimental_design || ''
  const normalized = raw.replaceAll('\r\n', '\n').trim()
  if (!normalized) {
    return []
  }
  const lines = normalized
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

  if (lines.length === 0) {
    return []
  }

  const numberedSteps = lines
    .map((line) => {
      const match = line.match(/^\d+\.\s+(.*)$/)
      return match ? match[1].trim() : ''
    })
    .filter(Boolean)

  return numberedSteps.length === lines.length ? numberedSteps : []
})

const reviewItems = [
  { key: 'initial_review', title: 'Initial Review', tone: 'green' },
  { key: 'full_review', title: 'Full Review', tone: 'blue' },
  { key: 'deep_verification_review', title: 'Deep Verification Review', tone: 'violet' },
  { key: 'observation_review', title: 'Observation Review', tone: 'orange' },
  { key: 'simulation_review', title: 'Simulation Review', tone: 'teal' }
] as const

const normalizeReviewItem = (reviewKey: string, item: string) => {
  if (reviewKey !== 'deep_verification_review') {
    return item
  }
  return item.replace(/^\s*-\s*/, '').trimStart()
}

const reviewCards = computed(() =>
  reviewItems.map((item) => {
    const section = props.hypothesis.review_sections.find((candidate) => candidate.key === item.key)
    const normalizedSection = section
      ? {
          ...section,
          entries: section.entries.map((entry) => ({
            ...entry,
            items: entry.items.map((entryItem) => normalizeReviewItem(item.key, entryItem))
          }))
        }
      : {
          key: item.key,
          title: item.title,
          verdict: null,
          entries: []
        }
    return {
      ...item,
      section: normalizedSection
    }
  })
)

const panelStyle = computed(() => {
  if (!props.panelHeight || props.panelHeight <= 0) {
    return undefined
  }

  const height = `${props.panelHeight}px`
  return {
    height,
    maxHeight: height
  }
})
</script>

<template>
  <div class="glass-card detail-panel" :style="panelStyle">
    <div class="detail-header">
      <div class="detail-header-copy">
        <div class="detail-alias-badge">{{ hypothesis.alias }}</div>
        <div class="detail-title">Hypothesis Detail</div>
      </div>
    </div>

    <div class="detail-grid">
      <div class="detail-card blue">
        <div class="detail-card-label">ELO Rating</div>
        <div class="detail-card-value">{{ hypothesis.elo_rating }}</div>
      </div>
      <div class="detail-card violet">
        <div class="detail-card-label">Rank</div>
        <div class="detail-card-value">{{ rankLabel }}</div>
      </div>
    </div>

    <div class="detail-block">
      <div class="detail-label">METHOD</div>
      <div class="detail-surface blue">
        <span class="detail-tag">{{ strategyLabel(hypothesis.origin.strategy) }}</span>
      </div>
    </div>

    <div class="detail-block">
      <div class="detail-label">CATEGORY</div>
      <div class="detail-surface blue">
        <span class="detail-tag">{{ hypothesis.origin.content.category }}</span>
      </div>
    </div>

    <div class="detail-block">
      <div class="detail-label">SUMMARY</div>
      <div class="detail-surface">{{ hypothesis.origin.content.summary }}</div>
    </div>

    <div class="detail-block">
      <div class="detail-label detail-label-warm">STATEMENT</div>
      <div class="detail-surface orange">{{ hypothesis.origin.content.statement }}</div>
    </div>

    <div class="detail-block">
      <div class="detail-label detail-label-violet">MECHANISM</div>
      <div class="detail-surface violet">{{ hypothesis.origin.content.mechanism }}</div>
    </div>

    <div class="detail-block">
      <div class="detail-label detail-label-teal">EXPERIMENTAL DESIGN</div>
      <div class="detail-surface teal">
        <ol v-if="experimentalDesignSteps.length" class="detail-ordered-list">
          <li v-for="step in experimentalDesignSteps" :key="step">{{ step }}</li>
        </ol>
        <div v-else class="detail-preformatted">{{ hypothesis.origin.content.experimental_design }}</div>
      </div>
    </div>

    <div class="detail-block">
      <div class="detail-label">METADATA</div>
      <div class="detail-surface">
        <div class="detail-meta-row">
          <div class="detail-meta-label">TIMESTAMP</div>
          <div class="detail-meta-value">{{ hypothesis.timestamp }}</div>
        </div>
        <div class="detail-meta-row">
          <div class="detail-meta-label">ID</div>
          <div class="detail-meta-value">{{ hypothesis.alias }}</div>
        </div>
        <div class="detail-meta-row">
          <div class="detail-meta-label">PARENTS ID</div>
          <div class="detail-meta-value">{{ parentSummary }}</div>
        </div>
        <div class="detail-meta-row">
          <div class="detail-meta-label">ISLAND ID</div>
          <div class="detail-meta-value">{{ islandSummary }}</div>
        </div>
      </div>
    </div>

    <div class="detail-block">
      <div class="detail-label">REVIEWS</div>
      <div class="review-list">
        <div
          v-for="card in reviewCards"
          :key="card.key"
          class="review-item"
          :class="card.tone"
        >
          <div class="review-item-header">
            <strong>{{ card.title }}</strong>
            <div
              v-if="card.section.verdict"
              class="review-verdict"
              :class="card.section.verdict.toLowerCase()"
            >
              {{ card.section.verdict }}
            </div>
          </div>
          <div
            v-for="entry in card.section.entries"
            :key="`${card.key}-${entry.label}`"
            class="review-entry"
          >
            <div class="review-entry-label">{{ entry.label }}</div>
            <div v-if="entry.content" class="review-entry-content">{{ entry.content }}</div>
            <ul v-if="entry.items.length" class="review-bullet-list">
              <li v-for="item in entry.items" :key="item">{{ item }}</li>
            </ul>
          </div>
          <div v-if="card.section.entries.length === 0" class="review-empty">
            No completed fields yet.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
