<script setup lang="ts">
import { ref } from 'vue'

definePageMeta({
  title: 'Evolution Graph',
  icon: 'git-branch',
  nav: 'evolution'
})

const { state, ranking, graphSeed, pending, error, hasData, runId } = useDashboardState()
const {
  selectedHypothesisId,
  selectedHypothesis,
  selectedRank,
  selectedDisplayTitle,
  selectHypothesis
} = useHypothesisSelection(state, ranking)
const contentColumnRef = ref<HTMLElement | null>(null)
const detailPanelHeight = useMatchedPanelHeight(contentColumnRef)
</script>

<template>
  <DashboardStateCard
    v-if="error && !hasData"
    title="Graph unavailable"
    :message="error"
    tone="error"
  />
  <DashboardStateCard
    v-else-if="pending && !hasData"
    title="Loading graph"
    message="Building the latest evolution graph from the live dashboard snapshot."
  />
  <DashboardStateCard
    v-else-if="!hasData || ranking.length === 0 || !selectedHypothesis"
    :title="runId ? 'No graph data yet' : 'No runs found'"
    :message="
      runId
        ? `Run ${runId} does not have enough saved state to render the evolution graph yet.`
        : 'No valid run directories were discovered under /runs.'
    "
  />
  <div v-else class="content-grid">
    <div ref="contentColumnRef">
      <GlassCard class="graph-card">
        <EvolutionGraphCanvas
          :graph-seed="graphSeed"
          :selected-id="selectedHypothesisId || undefined"
          @select="selectHypothesis"
        />
      </GlassCard>
    </div>

    <HypothesisDetailPanel
      :hypothesis="selectedHypothesis"
      :rank="selectedRank"
      :display-title="selectedDisplayTitle"
      :panel-height="detailPanelHeight"
    />
  </div>
</template>
