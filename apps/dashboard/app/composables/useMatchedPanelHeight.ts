import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Ref, WatchStopHandle } from 'vue'

const DESKTOP_BREAKPOINT = 1200

export const useMatchedPanelHeight = (sourceRef: Ref<HTMLElement | null>) => {
  const panelHeight = ref<number | null>(null)
  let resizeObserver: ResizeObserver | null = null
  let stopWatching: WatchStopHandle | null = null

  const updateHeight = () => {
    if (typeof window === 'undefined' || window.innerWidth <= DESKTOP_BREAKPOINT) {
      panelHeight.value = null
      return
    }

    const source = sourceRef.value
    if (!source) {
      panelHeight.value = null
      return
    }

    panelHeight.value = Math.round(source.getBoundingClientRect().height)
  }

  onMounted(() => {
    stopWatching = watch(
      sourceRef,
      (element) => {
        resizeObserver?.disconnect()
        if (element && typeof ResizeObserver !== 'undefined') {
          resizeObserver = new ResizeObserver(() => {
            updateHeight()
          })
          resizeObserver.observe(element)
        }
        updateHeight()
      },
      { immediate: true }
    )

    window.addEventListener('resize', updateHeight)
  })

  onBeforeUnmount(() => {
    resizeObserver?.disconnect()
    stopWatching?.()
    if (typeof window !== 'undefined') {
      window.removeEventListener('resize', updateHeight)
    }
  })

  return panelHeight
}
