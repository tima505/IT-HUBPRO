<template>
  <span class="badge" :class="cls"><Icon :name="icon" :size="13" /> {{ text }}</span>
</template>

<script setup>
import { computed } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({ status: { type: Object, default: null } })

const map = {
  early:   { cls: 'green', icon: 'check-circle', text: (d) => `Сдан раньше срока на ${d} дн.` },
  ontime:  { cls: 'green', icon: 'check-circle', text: () => 'Сдан точно в срок' },
  late:    { cls: 'red',   icon: 'alert',        text: (d) => `Сдан позже срока на ${d} дн.` },
  pending: { cls: 'blue',  icon: 'clock',        text: (d) => `До дедлайна ${d} дн.` },
  overdue: { cls: 'red',   icon: 'alert',        text: (d) => `Просрочен на ${d} дн.` },
}

const info = computed(() => map[props.status?.state] || map.pending)
const cls = computed(() => info.value.cls)
const icon = computed(() => info.value.icon)
const text = computed(() => info.value.text(props.status?.days ?? 0))
</script>
