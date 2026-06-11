<script setup lang="ts">
import type { PipelineStage } from '~/types/coScientist'

type AgentKey =
  | 'configuration'
  | 'generation'
  | 'supervisor'
  | 'evolution'
  | 'reflection'
  | 'insights'
  | 'proximity'
  | 'ranking'
  | 'researchOverview'

const props = defineProps<{
  currentStage: PipelineStage
}>()

const stageForAgent: Record<Exclude<AgentKey, 'supervisor'>, PipelineStage> = {
  configuration: 'Configuration',
  generation: 'Generation',
  evolution: 'Evolution',
  reflection: 'Reflection',
  insights: 'Insights from Reviews',
  proximity: 'Proximity',
  ranking: 'Ranking',
  researchOverview: 'Research Overview'
}

const nodeStateClass = (agent: AgentKey): 'active' | '' => {
  if (agent === 'supervisor') {
    return ''
  }
  return props.currentStage === stageForAgent[agent] ? 'active' : ''
}
</script>

<template>
  <GlassCard class="card-pad">
    <div class="agent-flowchart-shell">
      <div class="agent-flowchart">
        <svg
          class="agent-flowchart-lines"
          viewBox="0 0 946 164"
          preserveAspectRatio="xMinYMin meet"
          aria-hidden="true"
        >
          <defs>
            <marker
              id="agent-flow-arrow"
              markerWidth="9"
              markerHeight="9"
              refX="7.2"
              refY="4.5"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M1,1 L8,4.5 L1,8" class="agent-flow-arrowhead" />
            </marker>
          </defs>

          <path
            class="agent-flow-line"
            d="M182 39 H200"
            marker-end="url(#agent-flow-arrow)"
          />
          <path
            class="agent-flow-line"
            d="M182 117 H200"
            marker-end="url(#agent-flow-arrow)"
          />
          <path
            class="agent-flow-line"
            d="M370 39 H386"
            marker-end="url(#agent-flow-arrow)"
          />
          <path
            class="agent-flow-line"
            d="M370 117 H448 Q474 117 474 93 V69"
            marker-end="url(#agent-flow-arrow)"
          />
          <path
            class="agent-flow-line"
            d="M556 39 H572"
            marker-end="url(#agent-flow-arrow)"
          />
          <path
            class="agent-flow-line"
            d="M660 63 V90"
            marker-end="url(#agent-flow-arrow)"
          />
          <path
            class="agent-flow-line"
            d="M742 117 H758"
            marker-end="url(#agent-flow-arrow)"
          />
        </svg>

        <div class="agent-node flow-config" :class="nodeStateClass('configuration')">
          <span class="agent-node-label">Configuration Agent</span>
        </div>

        <div class="agent-node flow-generation" :class="nodeStateClass('generation')">
          <span class="agent-node-label">Generation Agent</span>
        </div>

        <div class="agent-node flow-reflection" :class="nodeStateClass('reflection')">
          <span class="agent-node-label">Reflection Agent</span>
        </div>

        <div class="agent-node flow-insights" :class="nodeStateClass('insights')">
          <span class="agent-node-label">Insights from Reviews Agent</span>
        </div>

        <div class="agent-node flow-overview" :class="nodeStateClass('researchOverview')">
          <span class="agent-node-label">Research Overview Agent</span>
        </div>

        <div class="agent-node flow-supervisor" :class="nodeStateClass('supervisor')">
          <span class="agent-node-label">Supervisor Agent</span>
        </div>

        <div class="agent-node flow-evolution" :class="nodeStateClass('evolution')">
          <span class="agent-node-label">Evolution Agent</span>
        </div>

        <div class="agent-node flow-proximity" :class="nodeStateClass('proximity')">
          <span class="agent-node-label">Proximity Agent</span>
        </div>

        <div class="agent-node flow-ranking" :class="nodeStateClass('ranking')">
          <span class="agent-node-label">Ranking Agent</span>
        </div>
      </div>
    </div>
  </GlassCard>
</template>
