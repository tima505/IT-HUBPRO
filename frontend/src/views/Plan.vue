<template>
  <div class="plan-page">
    <!-- Управление: период, дата, чей план -->
    <div class="controls">
      <div class="segmented">
        <button :class="{ active: period === 'day' }" @click="setPeriod('day')">День</button>
        <button :class="{ active: period === 'week' }" @click="setPeriod('week')">Неделя</button>
      </div>
      <div class="date-nav">
        <button class="btn ghost icon-btn" @click="shift(-1)" aria-label="Назад"><Icon name="chevron-left" :size="18" /></button>
        <div class="date-label">
          <b>{{ periodTitle }}</b>
          <span class="muted small">{{ periodSub }}</span>
        </div>
        <button class="btn ghost icon-btn" @click="shift(1)" aria-label="Вперёд"><Icon name="chevron-right" :size="18" /></button>
        <button v-if="!isCurrent" class="btn sm" @click="toToday">{{ period === 'day' ? 'Сегодня' : 'Эта неделя' }}</button>
      </div>
      <select v-if="auth.isAdmin" v-model="viewUser" class="select input who">
        <option :value="null">Мой план</option>
        <option v-for="u in team" :key="u.id" :value="u.id" :disabled="u.id === auth.user?.id">{{ u.name }}</option>
      </select>
    </div>

    <div class="plan-grid">
      <!-- Список -->
      <section class="card list-card">
        <div class="list-head">
          <div class="ring" :style="{ '--p': progress }">
            <span class="mono">{{ items.length ? progress + '%' : '—' }}</span>
          </div>
          <div class="grow">
            <div class="eyebrow">{{ readOnly ? viewName : (period === 'day' ? 'План на день' : 'План на неделю') }}</div>
            <h2 class="h2">{{ doneCount }} из {{ items.length }} выполнено</h2>
            <div v-if="carriedCount" class="muted small">{{ carriedCount }} перенесено дальше</div>
          </div>
        </div>

        <!-- перенос невыполненного -->
        <div v-if="!readOnly && isPast && undoneCount" class="banner warn">
          <Icon name="alert" :size="16" />
          <span class="grow">Не выполнено: {{ undoneCount }}.</span>
          <button class="btn sm" @click="carry(viewDate, todayKey)"><Icon name="arrow-right" :size="14" /> Перенести на {{ period === 'day' ? 'сегодня' : 'эту неделю' }}</button>
        </div>
        <div v-else-if="!readOnly && isCurrent && prevUndone" class="banner">
          <Icon name="undo" :size="16" />
          <span class="grow">С {{ period === 'day' ? 'прошлого дня' : 'прошлой недели' }} осталось невыполненных: {{ prevUndone }}.</span>
          <button class="btn sm" @click="carry(prevKey, viewDate)">Перенести сюда</button>
        </div>

        <form v-if="!readOnly" class="add" @submit.prevent="add">
          <input ref="addInput" v-model="newTitle" class="input" maxlength="300"
                 :placeholder="period === 'day' ? 'Что сделать сегодня? Enter — добавить' : 'Цель на неделю… Enter — добавить'" />
          <button class="btn primary icon-btn" :disabled="!newTitle.trim() || busy" aria-label="Добавить"><Icon name="plus" :size="18" /></button>
        </form>

        <transition-group name="list" tag="ul" class="items">
          <li v-for="it in items" :key="it.id" class="item" :class="{ done: it.is_done, carried: it.carried }">
            <label class="check" :class="{ disabled: readOnly || it.carried }">
              <input type="checkbox" :checked="it.is_done" :disabled="readOnly || it.carried" @change="toggle(it)" />
              <span class="box"><Icon name="check" :size="14" :stroke-width="3" /></span>
            </label>
            <input v-if="editingId === it.id" v-model="editTitle" class="input edit" maxlength="300"
                   @keydown.enter.prevent="saveEdit(it)" @keydown.esc="editingId = null" @blur="saveEdit(it)" />
            <span v-else class="title grow" @dblclick="startEdit(it)">{{ it.title }}</span>
            <span v-if="it.carried" class="badge gray">перенесено</span>
            <template v-if="!readOnly && !it.carried && editingId !== it.id">
              <button class="btn ghost sm icon-btn act" title="Изменить" @click="startEdit(it)"><Icon name="edit" :size="14" /></button>
              <button class="btn ghost sm icon-btn act del" title="Удалить" @click="remove(it)"><Icon name="trash" :size="14" /></button>
            </template>
          </li>
        </transition-group>

        <div v-if="loaded && !items.length" class="empty small">
          <div class="empty-ico"><Icon name="list-checks" :size="22" /></div>
          {{ readOnly ? 'На этот период ничего не запланировано' : (period === 'day' ? 'Запишите 3–5 главных дел на день' : 'Запишите цели на неделю') }}
        </div>
      </section>

      <!-- Статистика -->
      <section class="stats-col">
        <div class="tiles">
          <div class="card tile">
            <span class="tile-ico streak"><Icon name="zap" :size="18" /></span>
            <b class="mono">{{ stats?.streak ?? '—' }}</b>
            <span class="muted small">{{ plural(stats?.streak || 0, 'день', 'дня', 'дней') }} подряд — план выполнен полностью</span>
          </div>
          <div class="card tile">
            <span class="tile-ico rate"><Icon name="trending-up" :size="18" /></span>
            <b class="mono">{{ stats?.summary.rate ?? '—' }}{{ stats?.summary.rate !== null && stats ? '%' : '' }}</b>
            <span class="muted small">выполнено за 2 недели ({{ stats?.summary.done || 0 }} из {{ stats?.summary.planned || 0 }})</span>
          </div>
          <div class="card tile">
            <span class="tile-ico perfect"><Icon name="trophy" :size="18" /></span>
            <b class="mono">{{ stats?.summary.perfect_days ?? '—' }}<span class="muted small"> / {{ stats?.summary.days_with_plan || 0 }}</span></b>
            <span class="muted small">идеальных дней из дней с планом</span>
          </div>
        </div>

        <div class="card">
          <h3 class="h2 sm">Выполнение по дням</h3>
          <div class="muted small">Доля выполненных пунктов дневного плана, последние 14 дней</div>
          <div class="chart" role="img" aria-label="Выполнение плана по дням за 14 дней">
            <div class="gridline" style="bottom: 100%"><span>100%</span></div>
            <div class="gridline" style="bottom: 50%"><span>50%</span></div>
            <div class="gridline" style="bottom: 0"><span>0</span></div>
            <div class="bars">
              <div v-for="(d, i) in stats?.days || []" :key="d.date" class="slot" :class="{ active: hover === i, today: d.date === todayIso }"
                   @mouseenter="hover = i" @mouseleave="hover = null" @click="openDay(d.date)">
                <div v-if="d.planned" class="bar" :style="{ height: Math.max(d.rate, 2) + '%' }"></div>
                <div v-else class="nobar"></div>
                <div v-if="hover === i" class="tip">
                  <b>{{ shortDate(d.date) }}</b>
                  <div v-if="d.planned">{{ d.done }} из {{ d.planned }} · {{ d.rate }}%</div>
                  <div v-else class="muted">плана не было</div>
                </div>
              </div>
            </div>
          </div>
          <div class="x-axis mono">
            <span v-for="(d, i) in stats?.days || []" :key="'x' + d.date">{{ i % 2 === 1 || i === 0 ? dayNum(d.date) : '' }}</span>
          </div>
        </div>

        <div class="card">
          <h3 class="h2 sm">По неделям</h3>
          <div class="muted small">Все пункты недели: дневные и недельные цели</div>
          <div class="weeks">
            <button v-for="w in [...(stats?.weeks || [])].reverse()" :key="w.week" class="week" @click="openWeek(w.week)">
              <span class="w-range small">{{ shortDate(w.week) }} – {{ shortDate(w.week_end) }}</span>
              <span class="progress grow" :class="{ ok: w.rate === 100 }"><span :style="{ width: (w.rate || 0) + '%' }"></span></span>
              <span class="mono small w-num">{{ w.planned ? `${w.done}/${w.planned}` : '—' }}</span>
            </button>
          </div>
        </div>
      </section>
    </div>

    <!-- Команда (админ) -->
    <section v-if="auth.isAdmin && team.length" class="card">
      <div class="row between wrap gap-8" style="margin-bottom: 12px">
        <div>
          <h2 class="h2">Планы команды</h2>
          <div class="muted small">Текущая неделя · нажмите на человека, чтобы открыть его план</div>
        </div>
      </div>
      <div class="team">
        <button v-for="u in team" :key="u.id" class="member" :class="{ on: viewUser === u.id }" @click="viewUser = u.id === auth.user?.id ? null : u.id">
          <span class="avatar sm">{{ initials(u.name) }}</span>
          <span class="m-name grow">
            <b class="ellipsis">{{ u.name }}</b>
            <span class="muted small">сегодня {{ u.today_done }}/{{ u.today_planned }}</span>
          </span>
          <span class="m-bar"><span class="progress" :class="{ ok: u.week_rate === 100 }"><span :style="{ width: (u.week_rate || 0) + '%' }"></span></span></span>
          <span class="mono m-num">{{ u.week_planned ? `${u.week_done}/${u.week_planned}` : 'нет плана' }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import api from '../api'
import { useAuth } from '../stores/auth'
import Icon from '../components/Icon.vue'

const auth = useAuth()
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
const WEEKDAYS = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота']

// --- даты (локальные, без часовых поясов)
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const parse = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d) }
const addDays = (s, n) => { const d = parse(s); d.setDate(d.getDate() + n); return iso(d) }
const monday = (s) => { const d = parse(s); const wd = (d.getDay() + 6) % 7; d.setDate(d.getDate() - wd); return iso(d) }
const todayIso = iso(new Date())
const shortDate = (s) => { const d = parse(s); return `${d.getDate()} ${MONTHS[d.getMonth()].slice(0, 3)}` }
const dayNum = (s) => parse(s).getDate()

const period = ref('day')
const viewDate = ref(todayIso)
const viewUser = ref(null)
const items = ref([])
const prevItems = ref([])
const stats = ref(null)
const team = ref([])
const loaded = ref(false)
const busy = ref(false)
const newTitle = ref('')
const addInput = ref(null)
const hover = ref(null)

const readOnly = computed(() => viewUser.value !== null)
const viewName = computed(() => team.value.find(u => u.id === viewUser.value)?.name || '')
const todayKey = computed(() => (period.value === 'day' ? todayIso : monday(todayIso)))
const prevKey = computed(() => addDays(viewDate.value, period.value === 'day' ? -1 : -7))
const isCurrent = computed(() => viewDate.value === todayKey.value)
const isPast = computed(() => viewDate.value < todayKey.value)

const periodTitle = computed(() => {
  const d = parse(viewDate.value)
  if (period.value === 'day') {
    if (viewDate.value === todayIso) return 'Сегодня'
    if (viewDate.value === addDays(todayIso, -1)) return 'Вчера'
    if (viewDate.value === addDays(todayIso, 1)) return 'Завтра'
    return `${d.getDate()} ${MONTHS[d.getMonth()]}`
  }
  return isCurrent.value ? 'Эта неделя' : (viewDate.value === addDays(todayKey.value, 7) ? 'Следующая неделя' : 'Неделя')
})
const periodSub = computed(() => {
  const d = parse(viewDate.value)
  if (period.value === 'day') return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`
  return `${shortDate(viewDate.value)} – ${shortDate(addDays(viewDate.value, 6))}`
})

const doneCount = computed(() => items.value.filter(i => i.is_done).length)
const carriedCount = computed(() => items.value.filter(i => i.carried).length)
const undoneCount = computed(() => items.value.filter(i => !i.is_done && !i.carried).length)
const prevUndone = computed(() => prevItems.value.filter(i => !i.is_done && !i.carried).length)
const progress = computed(() => (items.value.length ? Math.round(doneCount.value * 100 / items.value.length) : 0))

const params = (date) => ({ period: period.value, date, ...(viewUser.value ? { user: viewUser.value } : {}) })

async function loadItems() {
  const reqs = [api.get('/plan/', { params: params(viewDate.value) })]
  if (!readOnly.value && isCurrent.value) reqs.push(api.get('/plan/', { params: params(prevKey.value) }))
  const [cur, prev] = await Promise.all(reqs)
  items.value = cur.data
  prevItems.value = prev?.data || []
  loaded.value = true
}
async function loadStats() {
  stats.value = (await api.get('/plan/stats/', { params: viewUser.value ? { user: viewUser.value } : {} })).data
  if (auth.isAdmin) team.value = (await api.get('/plan/team/')).data
}
async function reload() { await Promise.all([loadItems(), loadStats()]) }

function setPeriod(p) {
  period.value = p
  viewDate.value = p === 'day' ? todayIso : monday(todayIso)
}
function shift(n) { viewDate.value = addDays(viewDate.value, n * (period.value === 'day' ? 1 : 7)) }
function toToday() { viewDate.value = todayKey.value }
function openDay(date) { period.value = 'day'; viewDate.value = date }
function openWeek(week) { period.value = 'week'; viewDate.value = week }

watch([period, viewDate, viewUser], loadItems)
watch(viewUser, loadStats)

async function add() {
  const title = newTitle.value.trim()
  if (!title) return
  busy.value = true
  try {
    const { data } = await api.post('/plan/', { title, period: period.value, date: viewDate.value })
    items.value.push(data)
    newTitle.value = ''
    loadStats()
    await nextTick()
    addInput.value?.focus()
  } finally { busy.value = false }
}
async function toggle(it) {
  it.is_done = !it.is_done
  try {
    Object.assign(it, (await api.patch(`/plan/${it.id}/`, { is_done: it.is_done })).data)
    loadStats()
  } catch { it.is_done = !it.is_done }
}
async function remove(it) {
  await api.delete(`/plan/${it.id}/`)
  items.value = items.value.filter(x => x.id !== it.id)
  loadStats()
}
const editingId = ref(null)
const editTitle = ref('')
function startEdit(it) {
  if (readOnly.value || it.carried) return
  editingId.value = it.id
  editTitle.value = it.title
}
async function saveEdit(it) {
  if (editingId.value !== it.id) return
  editingId.value = null
  const title = editTitle.value.trim()
  if (!title || title === it.title) return
  Object.assign(it, (await api.patch(`/plan/${it.id}/`, { title })).data)
}
async function carry(from, to) {
  await api.post('/plan/carry_over/', { period: period.value, from_date: from, to_date: to })
  viewDate.value = to
  await reload()
}

function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100
  if (m10 === 1 && m100 !== 11) return one
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few
  return many
}
function initials(n = '') { return n.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase() }

onMounted(reload)
</script>

<style scoped>
.plan-page { display: flex; flex-direction: column; gap: 16px; }
.controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.date-nav { display: flex; align-items: center; gap: 6px; }
.date-label { display: flex; flex-direction: column; align-items: center; min-width: 170px; line-height: 1.25; }
.date-label b { font-size: 17px; }
.who { width: auto; min-width: 180px; margin-left: auto; }

.plan-grid { display: grid; grid-template-columns: 1.15fr 1fr; gap: 16px; align-items: start; }
.list-card { display: flex; flex-direction: column; gap: 14px; }
.list-head { display: flex; align-items: center; gap: 16px; }
.ring {
  --p: 0; width: 64px; height: 64px; border-radius: 50%; flex-shrink: 0; display: grid; place-items: center;
  background: conic-gradient(var(--c-blue) calc(var(--p) * 1%), var(--neutral-bg) 0);
  position: relative; font-weight: 700; font-size: 14px;
}
.ring::before { content: ''; position: absolute; inset: 6px; border-radius: 50%; background: var(--card); }
.ring span { position: relative; }

.banner { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 12px; border-radius: 12px;
  background: var(--info-bg); color: var(--text); font-size: 14px; }
.banner.warn { background: var(--warn-bg); }
.add { display: flex; gap: 8px; }
.items { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; position: relative; }
.item { display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-radius: 12px; background: var(--card-2);
  border: 1px solid var(--stroke); transition: background .2s, border-color .2s; }
.item:hover { border-color: var(--stroke-strong); }
.item .title { font-size: 14.5px; word-break: break-word; cursor: text; }
.item.done .title { color: var(--muted); text-decoration: line-through; text-decoration-color: var(--muted-2); }
.item.carried { opacity: .6; }
.item .act { opacity: 0; transition: opacity .2s; color: var(--muted); }
.item:hover .act { opacity: 1; }
.item .del:hover { color: var(--bad-fg); }
.edit { padding: 6px 10px; }
.check.disabled { cursor: default; }

.stats-col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.tile { display: flex; flex-direction: column; gap: 4px; padding: 14px; }
.tile b { font-size: 24px; letter-spacing: -.02em; }
.tile-ico { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; margin-bottom: 4px; }
.tile-ico.streak { background: var(--warn-bg); color: var(--warn-fg); }
.tile-ico.rate { background: var(--info-bg); color: var(--info-fg); }
.tile-ico.perfect { background: var(--ok-bg); color: var(--ok-fg); }
.h2.sm { font-size: 16px; }

.chart { position: relative; height: 140px; margin: 22px 0 4px 34px; }
.gridline { position: absolute; left: 0; right: 0; height: 1px; background: var(--stroke); }
.gridline span { position: absolute; right: calc(100% + 6px); transform: translateY(-50%); font-size: 10.5px; color: var(--muted-2); font-family: var(--font-mono); }
.bars { position: absolute; inset: 0; display: flex; align-items: flex-end; gap: 2px; }
.slot { position: relative; flex: 1; height: 100%; display: flex; align-items: flex-end; justify-content: center; cursor: pointer; border-radius: 6px 6px 0 0; }
.slot:hover, .slot.active { background: var(--hover); }
.bar { width: 100%; max-width: 22px; background: var(--c-blue); border-radius: 4px 4px 0 0; transition: height .5s cubic-bezier(.16,1,.3,1); }
.slot.today .bar { background: var(--accent); }
.nobar { width: 60%; max-width: 14px; height: 2px; background: var(--stroke-strong); border-radius: 2px; }
.tip { position: absolute; top: -4px; left: 50%; transform: translate(-50%, -100%); z-index: 5; white-space: nowrap; pointer-events: none;
  background: var(--panel-solid); border: 1px solid var(--stroke-strong); border-radius: 10px; padding: 6px 9px; font-size: 12px; box-shadow: var(--shadow); }
.x-axis { display: flex; gap: 2px; margin-left: 34px; font-size: 10.5px; color: var(--muted-2); }
.x-axis span { flex: 1; text-align: center; }

.weeks { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
.week { display: flex; align-items: center; gap: 12px; padding: 8px 10px; border-radius: 10px; border: 1px solid transparent;
  background: transparent; color: var(--text); font: inherit; cursor: pointer; text-align: left; }
.week:hover { background: var(--hover); }
.w-range { width: 120px; flex-shrink: 0; color: var(--muted); }
.w-num { width: 48px; text-align: right; }

.team { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(380px, 100%), 1fr)); gap: 8px; }
.member { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 12px; cursor: pointer; text-align: left;
  border: 1px solid var(--stroke); background: var(--card-2); color: var(--text); font: inherit; transition: border-color .2s; }
.member:hover { border-color: var(--stroke-strong); }
.member.on { border-color: var(--brand); background: var(--info-bg); }
.m-name { display: flex; flex-direction: column; min-width: 0; }
.m-bar { width: 110px; flex-shrink: 0; }
.m-num { width: 70px; text-align: right; font-size: 13px; }

@media (max-width: 1100px) { .plan-grid { grid-template-columns: 1fr; } }
@media (max-width: 640px) {
  .controls { gap: 8px; }
  .segmented { width: 100%; }
  .segmented button { flex: 1; }
  .date-nav { width: 100%; justify-content: space-between; }
  .date-label { min-width: 0; flex: 1; }
  .who { width: 100%; margin-left: 0; }
  .tiles { grid-template-columns: 1fr 1fr; }
  .tiles .tile:first-child { grid-column: 1 / -1; }
  .item .act { opacity: 1; }
  .m-bar { width: 70px; }
  .w-range { width: 100px; }
}
</style>
