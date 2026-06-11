import type { GraphData, GraphSeed, GraphSeedIsland, GraphSeedNode } from '~/types/coScientist'

const NODE_WIDTH = 80
const NODE_HEIGHT = 50
const LEVEL_GAP = 94
const NODE_GAP = 16
const ISLAND_TOP_PADDING = 108
const ISLAND_SIDE_PADDING = 16
const ISLAND_VERTICAL_GAP = 32
const CANVAS_PADDING = 18
const COLUMN_GAP = 28
const MIN_ISLAND_WIDTH = 220
const DEFAULT_LAYOUT_WIDTH = 680
const MAX_COLUMNS = 3

const toneCycle = ['blue', 'violet'] as const

const edgeColor = (tone: 'blue' | 'violet') => (tone === 'blue' ? '#60a5fa' : '#a78bfa')

const nodeTone = (tone: 'blue' | 'violet', index: number) => {
  if (tone === 'blue') {
    if (index === 0) return 'blue-900'
    if (index === 1) return 'blue-700'
    if (index === 2) return 'blue-600'
    if (index <= 4) return 'blue-500'
    return 'blue-300'
  }
  if (index === 0) return 'violet-900'
  if (index === 1) return 'violet-700'
  if (index === 2) return 'violet-500'
  return 'violet-300'
}

const buildLevels = (island: GraphSeedIsland) => {
  const adjacency = new Map<string, string[]>()
  const incoming = new Map<string, number>()
  island.nodes.forEach((node) => {
    adjacency.set(node.id, [])
    incoming.set(node.id, 0)
  })
  island.edges.forEach((edge) => {
    adjacency.get(edge.from)?.push(edge.to)
    incoming.set(edge.to, (incoming.get(edge.to) ?? 0) + 1)
  })

  const orderedNodes = [...island.nodes].sort((left, right) => right.score - left.score)
  const scoreById = new Map(orderedNodes.map((node) => [node.id, node.score]))
  adjacency.forEach((children) => {
    children.sort((left, right) => (scoreById.get(right) ?? 0) - (scoreById.get(left) ?? 0))
  })

  const levels = new Map<string, number>()
  const remainingIncoming = new Map(incoming)
  const roots = orderedNodes.filter((node) => (incoming.get(node.id) ?? 0) === 0)
  const queue = (roots.length > 0 ? roots : orderedNodes.slice(0, 1)).map((node) => node.id)
  const queued = new Set(queue)
  queue.forEach((nodeId) => {
    levels.set(nodeId, 0)
  })

  while (queue.length > 0) {
    const currentId = queue.shift()
    if (!currentId) continue
    const currentLevel = levels.get(currentId) ?? 0
    ;(adjacency.get(currentId) ?? []).forEach((childId) => {
      const nextLevel = currentLevel + 1
      levels.set(childId, Math.max(levels.get(childId) ?? nextLevel, nextLevel))
      const nextIncoming = (remainingIncoming.get(childId) ?? 0) - 1
      remainingIncoming.set(childId, nextIncoming)
      if (nextIncoming <= 0 && !queued.has(childId)) {
        queue.push(childId)
        queued.add(childId)
      }
    })
  }

  let nextFallbackLevel = levels.size > 0 ? Math.max(...levels.values()) + 1 : 0
  orderedNodes.forEach((node) => {
    if (levels.has(node.id)) return
    levels.set(node.id, nextFallbackLevel)
    nextFallbackLevel += 1
  })

  const grouped = new Map<number, GraphSeedNode[]>()
  orderedNodes.forEach((node) => {
    const level = levels.get(node.id) ?? nextFallbackLevel
    grouped.set(level, [...(grouped.get(level) ?? []), node])
  })

  return [...grouped.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([, nodes]) => nodes.sort((left, right) => right.score - left.score))
}

const formatMetric = (value: number) => {
  return Number.isInteger(value) ? `${value}` : value.toFixed(3)
}

const layoutIsland = (island: GraphSeedIsland, islandIndex: number) => {
  const tone = toneCycle[islandIndex % toneCycle.length]
  const levels = buildLevels(island)
  const maxRowWidth = Math.max(
    ...levels.map((levelNodes) => levelNodes.length * NODE_WIDTH + Math.max(0, levelNodes.length - 1) * NODE_GAP),
    NODE_WIDTH
  )
  const width = Math.max(MIN_ISLAND_WIDTH, maxRowWidth + ISLAND_SIDE_PADDING * 2)
  const orderedNodes = [...island.nodes].sort((left, right) => right.score - left.score)
  const nodes = levels.flatMap((levelNodes, levelIndex) => {
    const rowWidth = levelNodes.length * NODE_WIDTH + Math.max(0, levelNodes.length - 1) * NODE_GAP
    const startX = Math.max(ISLAND_SIDE_PADDING, (width - rowWidth) / 2)
    const y = ISLAND_TOP_PADDING + levelIndex * LEVEL_GAP
    return levelNodes.map((node, nodeIndex) => ({
      id: node.id,
      x: startX + nodeIndex * (NODE_WIDTH + NODE_GAP),
      y,
      label: node.label,
      score: node.score,
      tone: nodeTone(tone, orderedNodes.findIndex((item) => item.id === node.id))
    }))
  })
  const deepestNodeY = nodes.reduce((maxY, node) => Math.max(maxY, node.y), ISLAND_TOP_PADDING)
  const height = Math.max(240, deepestNodeY + NODE_HEIGHT + 28)

  return {
    id: island.id,
    x: 0,
    y: 0,
    width,
    height,
    tone,
    lines: [],
    arrows: [],
    edges: island.edges.map((edge) => ({
      ...edge,
      color: edgeColor(tone)
    })),
    nodes,
    metrics: {
      x: 16,
      y: 14,
      lines: [
        `Island ${island.metrics.alias}`,
        `Decayed Reward: ${formatMetric(island.metrics.decayedReward)}`,
        `Decayed Visits: ${formatMetric(island.metrics.decayedVisits)}`,
        `Visit Count: ${island.metrics.visitCount}`
      ]
    }
  } as GraphData['islands'][number]
}

const assignToColumns = (laidOutIslands: GraphData['islands'], columnCount: number) => {
  const columns = Array.from({ length: Math.max(1, columnCount) }, () => ({
    width: 0,
    height: CANVAS_PADDING,
    items: [] as Array<{ index: number; island: GraphData['islands'][number] }>
  }))

  laidOutIslands.forEach((island, index) => {
    const targetColumn = columns.reduce((bestIndex, column, columnIndex) => {
      return column.height < columns[bestIndex].height ? columnIndex : bestIndex
    }, 0)
    columns[targetColumn].items.push({ index, island })
    columns[targetColumn].width = Math.max(columns[targetColumn].width, island.width)
    columns[targetColumn].height += island.height + ISLAND_VERTICAL_GAP
  })

  return columns
}

const totalLayoutWidth = (
  columns: Array<{
    width: number
    height: number
    items: Array<{ index: number; island: GraphData['islands'][number] }>
  }>
) => columns.reduce((sum, column) => sum + column.width, 0) + CANVAS_PADDING * 2 + COLUMN_GAP * Math.max(0, columns.length - 1)

const buildColumnLayout = (seed: GraphSeed, columnCount: number) => {
  const laidOutIslands = seed.islands.map((island, index) => layoutIsland(island, index))
  const columns = assignToColumns(laidOutIslands, columnCount)
  return { laidOutIslands, columns }
}

export const buildGraphData = (seed: GraphSeed, options?: { maxWidth?: number }): GraphData => {
  if (seed.islands.length === 0) {
    return {
      islands: [],
      crossLines: [],
      crossArrows: [],
      crossEdges: []
    }
  }

  const maxWidth = Math.max(MIN_ISLAND_WIDTH + CANVAS_PADDING * 2, Math.floor(options?.maxWidth ?? DEFAULT_LAYOUT_WIDTH))
  const maxColumnCount = Math.min(MAX_COLUMNS, seed.islands.length)
  let columns = buildColumnLayout(seed, 1).columns

  // Prefer denser multi-column layouts first, then fall back until everything fits.
  for (let columnCount = maxColumnCount; columnCount >= 1; columnCount -= 1) {
    const candidate = buildColumnLayout(seed, columnCount)
    if (columnCount === 1 || totalLayoutWidth(candidate.columns) <= maxWidth) {
      columns = candidate.columns
      break
    }
  }

  const columnOffsets = columns.map((_, columnIndex) =>
    columns
      .slice(0, columnIndex)
      .reduce((offset, column) => offset + column.width + COLUMN_GAP, CANVAS_PADDING)
  )

  const islands = new Array<GraphData['islands'][number]>(seed.islands.length)
  columns.forEach((column, columnIndex) => {
    let offsetY = CANVAS_PADDING
    column.items.forEach(({ index, island }) => {
      islands[index] = {
        ...island,
        x: columnOffsets[columnIndex] + Math.round((column.width - island.width) / 2),
        y: offsetY
      }
      offsetY += island.height + ISLAND_VERTICAL_GAP
    })
  })

  return {
    islands,
    crossLines: [],
    crossArrows: [],
    crossEdges: seed.crossEdges.map((edge) => ({
      ...edge,
      color: 'var(--graph-cross-edge)',
      variant: 'cross'
    }))
  }
}
