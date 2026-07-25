<template>
  <div class="card stat" :style="{ '--accent-col': color }">
    <div class="row between">
      <div class="icon"><Icon :name="icon" :size="20" /></div>
      <span v-if="badge" class="badge" :class="badgeType">{{ badge }}</span>
    </div>
    <div class="value mono">{{ display }}</div>
    <div class="label muted small">{{ label }}</div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { money } from '../api'
import Icon from './Icon.vue'

const props = defineProps({
  label: String,
  value: [Number, String],
  icon: String,
  color: { type: String, default: '#6366f1' },
  isMoney: { type: Boolean, default: true },
  badge: String,
  badgeType: { type: String, default: 'gray' },
})

const display = ref('')
function render(v) {
  display.value = props.isMoney ? money(v) : String(v)
}

// плавный счётчик
function animate(to) {
  const target = Number(to) || 0
  const start = 0
  const dur = 700
  const t0 = performance.now()
  function step(now) {
    const p = Math.min((now - t0) / dur, 1)
    const eased = 1 - Math.pow(1 - p, 3)
    render(Math.round(target * eased))
    if (p < 1) requestAnimationFrame(step)
  }
  requestAnimationFrame(step)
}

onMounted(() => {
  if (typeof props.value === 'number') animate(props.value)
  else render(props.value)
})
watch(() => props.value, (v) => {
  if (typeof v === 'number') animate(v)
  else render(v)
})
</script>

<style scoped>
.stat { position: relative; overflow: hidden; }
.stat::before {
  content: ''; position: absolute; inset: 0;
  background: radial-gradient(120px 80px at 90% 0%, color-mix(in srgb, var(--accent-col) 30%, transparent), transparent 70%);
  pointer-events: none;
}
.icon {
  width: 42px; height: 42px; border-radius: 12px; display: grid; place-items: center;
  color: var(--accent-col);
  background: color-mix(in srgb, var(--accent-col) 16%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent-col) 32%, transparent);
}
.value { font-size: 26px; font-weight: 800; margin-top: 16px; letter-spacing: -.02em; }
.label { margin-top: 4px; }
</style>
