<script setup lang="ts">
import { computed, ref } from 'vue'

definePageMeta({
  title: 'Ranking',
  icon: 'trophy',
  nav: 'ranking'
})

const {
  state,
  ranking,
  pending,
  error,
  hasData,
  runId,
  currentStage
} = useDashboardState()
const {
  selectedHypothesisId,
  selectedHypothesis,
  selectedRank,
  selectedDisplayTitle,
  selectHypothesis
} = useHypothesisSelection(state, ranking)
const contentColumnRef = ref<HTMLElement | null>(null)
const detailPanelHeight = useMatchedPanelHeight(contentColumnRef)

const toneClass = (tone: string) => {
  return tone === 'violet' ? 'violet' : tone === 'cyan' ? 'cyan' : 'blue'
}

const hasGeneratedHypotheses = computed(() => Object.keys(state.value.hypotheses).length > 0)

const rankingStatusTitle = computed(() => {
  return hasGeneratedHypotheses.value ? 'Ranking is forming' : 'Waiting for first hypothesis'
})

const rankingStatusMessage = computed(() => {
  if (hasGeneratedHypotheses.value) {
    return 'Generated hypotheses are being reviewed and compared. The flowchart above will keep updating until the first ranked result is available.'
  }
  return 'The research plan is ready. The first generated hypothesis will appear here as soon as it is written to the snapshot.'
})

</script>

<template>
  <DashboardStateCard
    v-if="error && !hasData"
    title="Dashboard unavailable"
    :message="error"
    tone="error"
  />
  <div v-else-if="!hasData && runId" class="stack">
    <div class="section-title">Pipeline Flowchart</div>
    <PipelineFlowchart
      :current-stage="currentStage"
    />
  </div>
  <DashboardStateCard
    v-else-if="pending && !hasData"
    title="Loading dashboard"
    message="Fetching the latest Co-Scientist snapshot from the artifact-backed dashboard service."
  />
  <DashboardStateCard
    v-else-if="!hasData && !runId"
    title="No runs found"
    message="No valid run directories were discovered under /runs."
  />
  <div v-else class="content-grid ranking-grid">
    <div ref="contentColumnRef" class="stack">
      <div class="section-title">Research Plan</div>
      <GlassCard class="card-pad">
        <div class="detail-label">RESEARCH GOAL</div>
        <p style="margin: 8px 0 16px; font-size: 14px; line-height: 1.5;">
          {{ state.research_plan.research_goal }}
        </p>
        <div class="pref-grid">
          <div>
            <div class="detail-label" style="color: #475569;">PREFERENCES</div>
            <div class="pref-card blue">
              <ul class="bullet-list">
                <li v-for="item in state.research_plan.preferences" :key="item">{{ item }}</li>
              </ul>
            </div>
          </div>
          <div>
            <div class="detail-label" style="color: #475569;">CONSTRAINTS</div>
            <div class="pref-card orange">
              <ul class="bullet-list">
                <li v-for="item in state.research_plan.constraints" :key="item">{{ item }}</li>
              </ul>
            </div>
          </div>
        </div>
      </GlassCard>

      <div class="section-title">Pipeline Flowchart</div>
      <PipelineFlowchart
        :current-stage="currentStage"
      />

      <div class="section-title">Hypothesis Ranking (by ELO)</div>
      <DashboardStateCard
        v-if="ranking.length === 0"
        :title="rankingStatusTitle"
        :message="rankingStatusMessage"
        full-width
      />
      <div v-else class="stack">
        <button
          v-for="item in ranking"
          :key="item.id"
          type="button"
          class="rank-item"
          :class="{ selected: item.id === selectedHypothesisId }"
          :aria-pressed="item.id === selectedHypothesisId"
          @click="selectHypothesis(item.id)"
        >
          <div class="rank-left">
            <div class="rank-badge" :class="toneClass(item.tone)">#{{ item.rank }}</div>
            <div>
              <div class="rank-title">{{ item.title }}</div>
              <div class="rank-subtitle">{{ item.subtitle }}</div>
            </div>
          </div>
          <div class="elo-badge" :class="toneClass(item.tone)">{{ item.elo }} ELO</div>
        </button>
      </div>
    </div>

    <HypothesisDetailPanel
      v-if="selectedHypothesis"
      :hypothesis="selectedHypothesis"
      :rank="selectedRank"
      :display-title="selectedDisplayTitle"
      :panel-height="detailPanelHeight"
    />
    <DashboardStateCard
      v-else
      title="Hypothesis detail pending"
      message="The first generated hypothesis will appear here as soon as it has been written to the live snapshot."
    />
  </div>
</template>
