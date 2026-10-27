<template>
  <div class="term">
    <div class="chips">
      <button v-for="o in OPTIONS" :key="o.m" type="button" class="chip" :class="{ on: months === o.m && !custom }" @click="pick(o.m)">{{ o.label }}</button>
      <button type="button" class="chip" :class="{ on: custom }" @click="custom = true; $emit('update:months', null)">Дней…</button>
      <input v-if="custom" :value="days" type="number" min="1" class="input days" placeholder="дней"
             @input="$emit('update:days', $event.target.value ? Number($event.target.value) : null)" />
    </div>
    <div v-if="until" class="muted small">Действует до <b>{{ until }}</b></div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

// Срок сервера: месяцы (календарные — 6 мес = до того же числа через полгода) или своё число дней
const props = defineProps({
  months: { type: Number, default: null },
  days: { type: Number, default: null },
  start: { type: String, default: '' }, // дата начала, ГГГГ-ММ-ДД — для подсказки «действует до»
})
const emit = defineEmits(['update:months', 'update:days'])
const OPTIONS = [
  { m: 1, label: '1 мес' }, { m: 3, label: '3 мес' }, { m: 6, label: '6 мес' },
  { m: 12, label: '1 год' }, { m: 24, label: '2 года' },
]
const custom = ref(!props.months && !!props.days)
watch(() => props.months, (m) => { if (m) custom.value = false })

function pick(m) {
  custom.value = false
  emit('update:months', m)
  emit('update:days', null)
}

const until = computed(() => {
  if (!props.start) return ''
  const [y, mo, d] = props.start.split('-').map(Number)
  let end
  if (props.months && !custom.value) {
    const total = mo - 1 + props.months
    const ty = y + Math.floor(total / 12), tm = total % 12
    const last = new Date(ty, tm + 1, 0).getDate()
    end = new Date(ty, tm, Math.min(d, last))
  } else if (props.days) {
    end = new Date(y, mo - 1, d + Number(props.days))
  } else return ''
  return end.toLocaleDateString('ru-RU')
})
</script>

<style scoped>
.term { display: flex; flex-direction: column; gap: 8px; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.chip { border: 1px solid var(--stroke); background: var(--card-2); color: var(--muted); font: 600 13px var(--font);
  padding: 7px 12px; border-radius: 99px; cursor: pointer; transition: all .2s; }
.chip:hover { color: var(--text); border-color: var(--stroke-strong); }
.chip.on { color: var(--brand-contrast); background: var(--brand); border-color: var(--brand); }
.days { width: 110px; padding: 7px 10px; }
</style>
