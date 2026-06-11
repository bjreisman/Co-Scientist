import { computed, readonly, ref, watch } from 'vue'
import type { Ref } from 'vue'
import type { CoScientistState, Hypothesis, RankingItem } from '~/types/coScientist'

const buildHypothesisDisplayTitle = (hypothesis: Hypothesis) => {
  const candidates = [
    hypothesis.origin.content.summary,
    hypothesis.origin.content.category,
    hypothesis.origin.content.statement,
    hypothesis.id
  ]
  return candidates.find((value) => value.trim().length > 0) ?? 'Untitled hypothesis'
}

export const useHypothesisSelection = (
  state: Readonly<Ref<CoScientistState>>,
  ranking: Readonly<Ref<RankingItem[]>>
) => {
  const selectedHypothesisId = ref('')

  const firstGeneratedHypothesisId = (nextState: CoScientistState) => {
    const ordered = Object.values(nextState.hypotheses).sort((left, right) => {
      const timeOrder = left.timestamp.localeCompare(right.timestamp)
      if (timeOrder !== 0) return timeOrder
      return left.id.localeCompare(right.id)
    })
    return ordered[0]?.id ?? ''
  }

  watch(
    [state, ranking],
    ([nextState, nextRanking]) => {
      if (selectedHypothesisId.value && nextState.hypotheses[selectedHypothesisId.value]) {
        return
      }

      if (nextRanking.length > 0) {
        selectedHypothesisId.value = nextRanking[0].id
        return
      }

      selectedHypothesisId.value = firstGeneratedHypothesisId(nextState)
    },
    { immediate: true }
  )

  const selectedRankingItem = computed(() => {
    if (!selectedHypothesisId.value) return ranking.value[0] ?? null
    return ranking.value.find((item) => item.id === selectedHypothesisId.value) ?? ranking.value[0] ?? null
  })

  const selectedHypothesis = computed(() => {
    const fallbackId = selectedRankingItem.value?.id ?? ''
    const hypothesisId = selectedHypothesisId.value || fallbackId
    return hypothesisId ? state.value.hypotheses[hypothesisId] ?? null : null
  })

  const selectedRank = computed(() => selectedRankingItem.value?.rank ?? null)
  const selectedDisplayTitle = computed(() =>
    selectedHypothesis.value ? buildHypothesisDisplayTitle(selectedHypothesis.value) : ''
  )

  const selectHypothesis = (hypothesisId: string) => {
    if (!state.value.hypotheses[hypothesisId]) return
    selectedHypothesisId.value = hypothesisId
  }

  return {
    selectedHypothesisId: readonly(selectedHypothesisId),
    selectedHypothesis,
    selectedRank,
    selectedDisplayTitle,
    selectHypothesis
  }
}
