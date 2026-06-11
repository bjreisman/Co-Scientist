<script setup lang="ts">
import {
  ArrowRight,
  BookOpen,
  Brain,
  ChevronRight,
  ChevronsUpDown,
  FileText,
  GitBranch,
  MessageSquare,
  Moon,
  Sun,
  Swords,
  Trophy,
  X
} from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{ name: string; size?: number; strokeWidth?: number }>(),
  { size: 18, strokeWidth: 2 }
)

const iconMap: Record<string, any> = {
  brain: Brain,
  'chevrons-up-down': ChevronsUpDown,
  trophy: Trophy,
  'git-branch': GitBranch,
  'file-text': FileText,
  'chevron-right': ChevronRight,
  sun: Sun,
  moon: Moon,
  x: X,
  'arrow-right': ArrowRight,
  'message-square': MessageSquare,
  swords: Swords,
  'book-open': BookOpen
}
</script>

<template>
  <component
    :is="iconMap[props.name]"
    :size="props.size"
    :stroke-width="props.strokeWidth"
    aria-hidden="true"
  />
</template>
