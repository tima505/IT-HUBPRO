<template>
  <span class="badge" :class="cls">{{ label }}</span>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ status: String })
const map = {
  active: ['green', 'В работе'],
  done: ['blue', 'Завершён'],
  cancelled: ['gray', 'Отменён'],
}
const cls = computed(() => map[props.status]?.[0] || 'gray')
const label = computed(() => map[props.status]?.[1] || props.status)
</script>
