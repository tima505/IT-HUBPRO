<template>
  <div>
    <p class="muted" style="margin-bottom: 16px">Всё, что происходило в системе: проекты, платежи, серверы, проверка и комментарии.</p>

    <div class="row gap-8 wrap" style="margin-bottom: 14px">
      <button v-for="t in types" :key="t.v" class="btn sm" :class="{ primary: type === t.v }" @click="type = t.v">
        <Icon :name="t.icon" :size="15" /> {{ t.label }} <span class="count">{{ t.count }}</span>
      </button>
    </div>

    <FilterBar v-model:search="q" v-model:from="dateFrom" v-model:to="dateTo" dates
      placeholder="Проект, человек, текст, сумма…" :count="shown.length" :total="byType.length"
      :extra-active="!!projectFilter" @reset="projectFilter = ''">
      <select v-model="projectFilter" class="select f-select">
        <option value="">Все проекты</option>
        <option v-for="p in projectOptions" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
    </FilterBar>

    <div v-if="loading" class="center" style="padding: 40px"><span class="spinner"></span></div>

    <template v-else>
      <div v-if="sumShown" class="sum card">
        <span class="muted small">Сумма денежных событий в выборке</span>
        <b class="mono">{{ money(sumShown) }}</b>
      </div>

      <div v-for="g in groups" :key="g.date" class="day">
        <div class="day-head">
          <b>{{ dayLabel(g.date) }}</b>
          <span class="muted small">{{ g.items.length }} {{ plural(g.items.length) }}</span>
        </div>
        <div class="card tight">
          <div v-for="e in g.items" :key="e.id" class="ev" :class="{ link: e.project_id }" @click="openProject(e)">
            <div class="ev-ico" :class="e.type"><Icon :name="icons[e.type]" :size="17" /></div>
            <div class="grow ev-body">
              <div class="row between gap-8 wrap">
                <div class="row gap-8 wrap">
                  <b>{{ e.title }}</b>
                  <span v-if="e.project_name" class="muted">· {{ e.project_name }}</span>
                </div>
                <b v-if="e.amount" class="mono" :class="{ minus: e.type === 'server' }">
                  {{ e.type === 'server' ? '−' : '+' }} {{ money(e.amount) }}
                </b>
              </div>
              <div v-if="e.text" class="ev-text muted small">{{ e.text }}</div>
              <div v-if="e.who" class="muted small">{{ e.who }}</div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="hidden" class="more-row">
        <button class="btn ghost" @click="limit += 60">Показать ещё {{ Math.min(hidden, 60) }} из {{ hidden }}</button>
      </div>

      <div v-if="!shown.length" class="card center muted" style="padding: 50px">
        {{ events.length ? 'По фильтрам ничего не найдено' : 'Событий пока нет' }}
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api, { money, formatDate } from '../../api'
import Icon from '../../components/Icon.vue'
import FilterBar from '../../components/FilterBar.vue'
import { textMatch, inRange } from '../../filters'

const router = useRouter()
const events = ref([])
const loading = ref(true)

const icons = { project: 'folder', payment: 'wallet', server: 'server', review: 'check-circle', comment: 'message' }
const typeDefs = [
  { v: '', label: 'Все', icon: 'history' },
  { v: 'project', label: 'Проекты', icon: 'folder' },
  { v: 'payment', label: 'Платежи', icon: 'wallet' },
  { v: 'server', label: 'Серверы', icon: 'server' },
  { v: 'review', label: 'Проверка', icon: 'check-circle' },
  { v: 'comment', label: 'Комментарии', icon: 'message' },
]

const type = ref('')
const q = ref('')
const projectFilter = ref('')
const dateFrom = ref('')
const dateTo = ref('')

// всё, кроме вкладки типа, — чтобы счётчики на вкладках показывали найденное
const filteredBase = computed(() => events.value.filter(e =>
  textMatch(q.value, e.title, e.text, e.who, e.project_name, e.amount) &&
  (!projectFilter.value || e.project_id === projectFilter.value) &&
  inRange(e.date, dateFrom.value, dateTo.value)))
const types = computed(() => typeDefs.map(t => ({
  ...t, count: t.v ? filteredBase.value.filter(e => e.type === t.v).length : filteredBase.value.length,
})))
const byType = computed(() => (type.value ? events.value.filter(e => e.type === type.value) : events.value))
const shown = computed(() => (type.value ? filteredBase.value.filter(e => e.type === type.value) : filteredBase.value))

const projectOptions = computed(() => {
  const map = new Map()
  events.value.forEach(e => { if (e.project_id) map.set(e.project_id, e.project_name) })
  return [...map].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name, 'ru'))
})

// приход минус расход по выбранным событиям
const sumShown = computed(() => shown.value.reduce((acc, e) =>
  acc + (e.amount && e.type !== 'project' ? (e.type === 'server' ? -1 : 1) * Number(e.amount) : 0), 0))

const limit = ref(60)
watch([type, q, projectFilter, dateFrom, dateTo], () => { limit.value = 60 })
const hidden = computed(() => Math.max(0, shown.value.length - limit.value))
const groups = computed(() => {
  const out = []
  for (const e of shown.value.slice(0, limit.value)) {
    const last = out[out.length - 1]
    if (last && last.date === e.date) last.items.push(e)
    else out.push({ date: e.date, items: [e] })
  }
  return out
})

const todayIso = () => new Date().toISOString().slice(0, 10)
function dayLabel(d) {
  const t = new Date(); const y = new Date(t); y.setDate(t.getDate() - 1)
  if (d === todayIso()) return 'Сегодня'
  if (d === y.toISOString().slice(0, 10)) return 'Вчера'
  return formatDate(d)
}
function plural(n) {
  const m10 = n % 10, m100 = n % 100
  if (m10 === 1 && m100 !== 11) return 'событие'
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'события'
  return 'событий'
}

function openProject(e) { if (e.project_id) router.push(`/projects/${e.project_id}`) }

onMounted(async () => {
  try { events.value = (await api.get('/history/')).data }
  finally { loading.value = false }
})
</script>

<style scoped>
.count { opacity: .7; font-weight: 700; margin-left: 2px; }
.sum { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 18px; margin-bottom: 16px; }
.day { margin-bottom: 18px; }
.day-head { display: flex; align-items: baseline; gap: 10px; margin: 0 4px 8px; }
.ev { display: flex; gap: 14px; padding: 14px 18px; border-bottom: 1px solid var(--stroke); transition: background .15s; }
.ev:last-child { border-bottom: none; }
.ev.link { cursor: pointer; }
.ev.link:hover { background: var(--hover); }
.ev-ico { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 10px; flex-shrink: 0; background: var(--info-bg); color: var(--info-fg); }
.ev-ico.payment { background: var(--ok-bg); color: var(--ok-fg); }
.ev-ico.server { background: var(--warn-bg); color: var(--warn-fg); }
.ev-ico.review { background: var(--neutral-bg); color: var(--text); }
.ev-ico.comment { background: var(--card-2); color: var(--muted); }
.ev-body { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.ev-text { white-space: pre-wrap; word-break: break-word; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.minus { color: var(--bad-fg); }
.more-row { display: flex; justify-content: center; margin-top: 8px; }
</style>
