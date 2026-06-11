<script setup lang="ts">
const route = useRoute()
await navigateTo({
  path: '/ranking',
  query: route.query
})
</script>

<template>
  <div></div>
</template>
