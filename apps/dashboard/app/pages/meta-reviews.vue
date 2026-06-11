<script setup lang="ts">
definePageMeta({
  title: 'Meta-Reviews',
  icon: 'file-text',
  nav: 'meta'
})

const { insightSections, pending, error, hasData, runId } = useDashboardState()
</script>

<template>
  <DashboardStateCard
    v-if="error && !hasData"
    title="Meta-review unavailable"
    :message="error"
    tone="error"
  />
  <DashboardStateCard
    v-else-if="pending && !hasData"
    title="Loading meta-review"
    message="Fetching review insights and research overview from artifact-backed dashboard data."
  />
  <DashboardStateCard
    v-else-if="!hasData"
    :title="runId ? 'No meta-review yet' : 'No runs found'"
    :message="
      runId
        ? `Run ${runId} does not have a saved meta-review snapshot yet.`
        : 'No valid run directories were discovered under /runs.'
    "
  />
  <div v-else class="cards-grid meta-reviews-grid">
    <InsightCard v-for="section in insightSections" :key="section.title" :section="section" />
  </div>
</template>
