<template>
  <div class="fbar">
    <div class="search">
      <Icon name="search" :size="17" class="s-ico" />
      <input v-model="search" class="s-input" :placeholder="placeholder" />
      <button v-if="search" class="s-clear" title="Очистить" @click="search = ''"><Icon name="close" :size="14" /></button>
    </div>

    <!-- дополнительные фильтры страницы (select'ы) -->
    <slot />

    <template v-if="dates">
      <select v-model="period" class="select f-select" :title="dateLabel">
        <option v-for="p in PERIODS" :key="p.v" :value="p.v">{{ p.v ? p.label : `${dateLabel}: всё время` }}</option>
      </select>
      <transition name="pop">
        <div v-if="period === 'custom'" class="range">
          <input v-model="from" type="date" class="input f-date" title="С даты" />
          <span class="muted">—</span>
          <input v-model="to" type="date" class="input f-date" title="По дату" />
        </div>
      </transition>
    </template>

    <div class="tail">
      <span v-if="total != null && active" class="muted small">Найдено {{ count }} из {{ total }}</span>
      <button v-if="active" class="btn ghost sm" @click="reset"><Icon name="close" :size="14" /> Сбросить</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import Icon from './Icon.vue'
import { PERIODS, periodRange } from '../filters'

const props = defineProps({
  placeholder: { type: String, default: 'Поиск…' },
  dates: { type: Boolean, default: false },
  dateLabel: { type: String, default: 'Дата' },
  count: Number,
  total: Number,
  // страница сообщает, что её собственные фильтры (в слоте) тоже выбраны
  extraActive: Boolean,
})
const emit = defineEmits(['reset'])

const search = defineModel('search', { default: '' })
const from = defineModel('from', { default: '' })
const to = defineModel('to', { default: '' })

const period = ref('')
watch(period, (v) => {
  if (v === 'custom') return
  const [f, t] = periodRange(v)
  from.value = f
  to.value = t
})

const active = computed(() => !!(search.value || from.value || to.value || props.extraActive))

function reset() {
  search.value = ''
  period.value = ''
  from.value = ''
  to.value = ''
  emit('reset')
}
</script>

<style scoped>
.fbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; }
.search { position: relative; flex: 1 1 240px; max-width: 380px; }
.s-ico { position: absolute; left: 13px; top: 50%; transform: translateY(-50%); color: var(--muted); pointer-events: none; }
.s-input { width: 100%; padding: 10px 34px 10px 40px; border-radius: 11px; border: 1px solid var(--stroke-strong); background: var(--input-bg); color: var(--text); font: inherit; font-size: 14px; outline: none; transition: border-color .2s; }
.s-input:focus { border-color: var(--brand); }
.s-input::placeholder { color: var(--muted-2); }
.s-clear { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); display: grid; place-items: center; width: 22px; height: 22px; border-radius: 6px; border: none; background: var(--hover); color: var(--muted); cursor: pointer; }
.fbar :deep(.f-select) { width: auto; min-width: 170px; padding-top: 9px; padding-bottom: 9px; font-size: 14px; }
.range { display: flex; align-items: center; gap: 6px; }
.f-date { width: auto; padding-top: 8px; padding-bottom: 8px; font-size: 14px; }
.tail { display: flex; align-items: center; gap: 10px; margin-left: auto; }
@media (max-width: 640px) { .search { max-width: none; } .tail { margin-left: 0; } }
</style>
