<template>
  <span class="badge" :class="cls">{{ label }}</span>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ status: String })
const map = {
  none: ['gray', 'Не отправлен'],
  review: ['blue', 'На проверке'],
  returned: ['red', 'Возврат'],
  accepted: ['green', 'Принят'],
}
const cls = computed(() => map[props.status]?.[0] || 'gray')
const label = computed(() => map[props.status]?.[1] || props.status)
</script>
