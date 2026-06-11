<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { GraphData, GraphSeed } from '~/types/coScientist'
import { buildGraphData } from '~/utils/dashboardGraph'

const props = defineProps<{
  graphSeed: GraphSeed
  selectedId?: string
}>()
const emit = defineEmits<{
  select: [hypothesisId: string]
}>()
const canvasRef = ref<HTMLElement | null>(null)
const availableWidth = ref(0)
let resizeObserver: ResizeObserver | null = null

const syncWidth = () => {
  availableWidth.value = canvasRef.value?.clientWidth ?? 0
}

onMounted(() => {
  syncWidth()
  resizeObserver = new ResizeObserver(() => {
    syncWidth()
  })
  if (canvasRef.value) {
    resizeObserver.observe(canvasRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})

const graph = computed<GraphData>(() =>
  buildGraphData(props.graphSeed, {
    maxWidth: availableWidth.value || undefined
  })
)

const LINE_THICKNESS = 1.5
const DEFAULT_NODE_WIDTH = 80
const DEFAULT_NODE_HEIGHT = 50
const ARROW_SIZE = 15
const ARROW_INSET = 6

type GraphLine = GraphData['islands'][number]['lines'][number]
type GraphArrow = GraphData['islands'][number]['arrows'][number]
type GraphNode = GraphData['islands'][number]['nodes'][number]
type GraphEdge = NonNullable<GraphData['islands'][number]['edges']>[number]

const round2 = (value: number) => Math.round(value * 100) / 100
const toCssRotation = (rotation: number) => -rotation

const getOffset = (offset?: { x?: number; y?: number }) => ({
  x: offset?.x ?? 0,
  y: offset?.y ?? 0
})

const lineStyle = (line: GraphLine, offset?: { x?: number; y?: number }) => {
  const { x, y } = getOffset(offset)
  return {
    left: `${line.x + x}px`,
    top: `${line.y + y}px`,
    width: `${line.width}px`,
    height: `${LINE_THICKNESS}px`,
    transform: `rotate(${toCssRotation(line.rotation)}deg)`,
    color: line.color,
    '--graph-line-color': line.color
  }
}

const arrowStyle = (arrow: GraphArrow, offset?: { x?: number; y?: number }) => {
  const { x, y } = getOffset(offset)
  return {
    position: 'absolute',
    left: `${arrow.x + x}px`,
    top: `${arrow.y + y}px`,
    transform: `rotate(${toCssRotation(arrow.rotation)}deg)`,
    color: arrow.color
  }
}

const nodeBox = (node: GraphNode) => {
  const width = node.width ?? DEFAULT_NODE_WIDTH
  const height = node.height ?? DEFAULT_NODE_HEIGHT
  return {
    width,
    height,
    halfW: width / 2,
    halfH: height / 2,
    cx: node.x + width / 2,
    cy: node.y + height / 2
  }
}

const edgeEndpoint = (
  box: ReturnType<typeof nodeBox>,
  dx: number,
  dy: number
) => {
  const absDx = Math.abs(dx)
  const absDy = Math.abs(dy)
  if (absDx === 0 && absDy === 0) {
    return { x: box.cx, y: box.cy }
  }
  const scale = 1 / Math.max(absDx / box.halfW, absDy / box.halfH)
  return { x: box.cx + dx * scale, y: box.cy + dy * scale }
}

const buildEdgeGeometry = (edge: GraphEdge, from: GraphNode, to: GraphNode) => {
  const fromBox = nodeBox(from)
  const toBox = nodeBox(to)
  const dx = toBox.cx - fromBox.cx
  const dy = toBox.cy - fromBox.cy
  const start = edgeEndpoint(fromBox, dx, dy)
  const end = edgeEndpoint(toBox, -dx, -dy)
  const length = Math.hypot(end.x - start.x, end.y - start.y)
  if (!Number.isFinite(length) || length < 0.5) {
    return null
  }
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI
  const rotation = -angle
  const centerX = (start.x + end.x) / 2
  const centerY = (start.y + end.y) / 2
  const line: GraphLine = {
    id: edge.id,
    x: round2(centerX - length / 2),
    y: round2(centerY - LINE_THICKNESS / 2),
    width: round2(length),
    rotation: round2(rotation),
    color: edge.color,
    variant: edge.variant
  }
  const norm = Math.hypot(dx, dy) || 1
  const unitX = dx / norm
  const unitY = dy / norm
  const arrowCenterX = end.x - unitX * ARROW_INSET
  const arrowCenterY = end.y - unitY * ARROW_INSET
  const arrow: GraphArrow = {
    id: `${edge.id}-arrow`,
    x: round2(arrowCenterX - ARROW_SIZE / 2),
    y: round2(arrowCenterY - ARROW_SIZE / 2),
    rotation: round2(rotation),
    color: edge.color,
    variant: edge.variant
  }
  return { line, arrow }
}

const buildFromEdges = (edges: GraphEdge[], nodeMap: Map<string, GraphNode>) => {
  const lines: GraphLine[] = []
  const arrows: GraphArrow[] = []
  edges.forEach((edge) => {
    const from = nodeMap.get(edge.from)
    const to = nodeMap.get(edge.to)
    if (!from || !to) return
    const built = buildEdgeGeometry(edge, from, to)
    if (!built) return
    lines.push(built.line)
    arrows.push(built.arrow)
  })
  return { lines, arrows }
}

const resolvedIslands = computed(() =>
  graph.value.islands.map((island) => {
    if (!island.edges || island.edges.length === 0) {
      return { ...island, resolvedLines: island.lines, resolvedArrows: island.arrows }
    }
    const nodeMap = new Map(island.nodes.map((node) => [node.id, node]))
    const { lines, arrows } = buildFromEdges(island.edges, nodeMap)
    return { ...island, resolvedLines: lines, resolvedArrows: arrows }
  })
)

const resolvedCross = computed(() => {
  if (!graph.value.crossEdges || graph.value.crossEdges.length === 0) {
    return { lines: graph.value.crossLines, arrows: graph.value.crossArrows }
  }
  const nodeMap = new Map<string, GraphNode>()
  graph.value.islands.forEach((island) => {
    island.nodes.forEach((node) => {
      nodeMap.set(node.id, {
        ...node,
        x: node.x + island.x,
        y: node.y + island.y
      })
    })
  })
  return buildFromEdges(graph.value.crossEdges, nodeMap)
})

const canvasHeight = computed(() => {
  const islandBottom = graph.value.islands.reduce((maxBottom, island) => {
    return Math.max(maxBottom, island.y + island.height)
  }, 0)
  return Math.max(763, islandBottom + 32)
})
</script>

<template>
  <div ref="canvasRef" class="graph-canvas" :style="{ height: `${canvasHeight}px` }">
    <div
      v-for="island in resolvedIslands"
      :key="island.id"
      class="island"
      :class="island.tone"
      :style="{
        left: `${island.x}px`,
        top: `${island.y}px`,
        width: `${island.width}px`,
        height: `${island.height}px`
      }"
    >
      <div
        v-for="line in island.resolvedLines"
        :key="line.id"
        class="graph-line"
        :class="{ cross: line.variant === 'cross' }"
        :style="lineStyle(line, island.lineOffset)"
      ></div>
      <AppIcon
        v-for="arrow in island.resolvedArrows"
        :key="arrow.id"
        name="arrow-right"
        :size="15"
        class="graph-arrow"
        :class="{ cross: arrow.variant === 'cross' }"
        :style="arrowStyle(arrow, island.lineOffset)"
      />

      <button
        v-for="node in island.nodes"
        :key="node.id"
        type="button"
        class="graph-node"
        :class="[node.tone, { selected: node.id === props.selectedId }]"
        :style="{ left: `${node.x}px`, top: `${node.y}px` }"
        :aria-pressed="node.id === props.selectedId"
        @click="emit('select', node.id)"
      >
        <strong>{{ node.label }}</strong>
        <span>{{ node.score }}</span>
      </button>

      <div
        class="island-metrics"
        :class="island.tone === 'violet' ? 'violet' : ''"
        :style="{ left: `${island.metrics.x}px`, top: `${island.metrics.y}px` }"
      >
        <div v-for="line in island.metrics.lines" :key="line">{{ line }}</div>
      </div>
    </div>

    <div
      v-for="line in resolvedCross.lines"
      :key="line.id"
      class="graph-line"
      :class="{ cross: line.variant === 'cross' }"
      :style="lineStyle(line)"
    ></div>
    <AppIcon
      v-for="arrow in resolvedCross.arrows"
      :key="arrow.id"
      name="arrow-right"
      :size="15"
      class="graph-arrow"
      :class="{ cross: arrow.variant === 'cross' }"
      :style="arrowStyle(arrow)"
    />
  </div>
</template>
