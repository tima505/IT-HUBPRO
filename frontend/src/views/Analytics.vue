<template>
  <div class="analytics">
    <!-- Месяц + экспорт -->
    <div class="head-row no-print-controls">
      <div class="month-nav">
        <button class="btn ghost icon-btn" @click="shift(-1)" aria-label="Предыдущий месяц"><Icon name="chevron-left" :size="18" /></button>
        <div class="month-label">
          <div class="eyebrow">Отчёт</div>
          <b>{{ monthTitle }}</b>
        </div>
        <button class="btn ghost icon-btn" @click="shift(1)" :disabled="isCurrent" aria-label="Следующий месяц"><Icon name="chevron-right" :size="18" /></button>
      </div>
      <div class="row gap-8 no-print">
        <button class="btn sm" @click="exportCsv" :disabled="!report"><Icon name="download" :size="15" /> Excel (CSV)</button>
        <button class="btn sm ghost" @click="print"><Icon name="printer" :size="15" /> Печать</button>
      </div>
    </div>

    <template v-if="report">
      <!-- KPI -->
      <div class="kpis">
        <StatCard label="Выполнено задач" :value="t.done" icon="check-circle" color="#6366f1" :is-money="false" />
        <StatCard label="Выполнено в срок" :value="t.on_time_rate === null ? '—' : t.on_time_rate + '%'" icon="clock" color="#059669" :is-money="false"
                  :badge="t.late ? `${t.late} с опозданием` : ''" badge-type="amber" />
        <StatCard label="Просрочено" :value="t.overdue" icon="alert" color="#ef4444" :is-money="false"
                  :badge="t.overdue ? 'не сделаны' : ''" badge-type="red" />
        <StatCard label="Подзадач закрыто" :value="t.subtasks_done" icon="list-checks" color="#0ea5e9" :is-money="false"
                  :badge="t.in_work ? `${t.in_work} в работе сейчас` : ''" badge-type="blue" />
      </div>

      <!-- По дням -->
      <div class="card">
        <div class="row between wrap gap-8">
          <div>
            <h2 class="h2">Выполнено по дням</h2>
            <div class="muted small">Сколько задач переведено в «Готово» за каждый день месяца</div>
          </div>
          <div v-if="best" class="muted small">Лучший день: <b class="mono">{{ formatDate(best.date) }}</b> — {{ best.done }}</div>
        </div>

        <div class="chart" role="img" :aria-label="`Выполнено задач по дням за ${monthTitle}`">
          <div class="y-axis mono">
            <span v-for="tick in yTicks" :key="tick" :style="{ bottom: (tick / yMax * 100) + '%' }">{{ tick }}</span>
          </div>
          <div class="plot">
            <div v-for="tick in yTicks" :key="'g' + tick" class="gridline" :style="{ bottom: (tick / yMax * 100) + '%' }"></div>
            <div class="bars">
              <div v-for="(d, i) in report.by_day" :key="d.date" class="bar-slot"
                   :class="{ active: hover === i, today: d.date === todayIso }"
                   @mouseenter="hover = i" @mouseleave="hover = null" @click="hover = hover === i ? null : i">
                <div class="bar" :style="{ height: (d.done / yMax * 100) + '%' }"></div>
                <div v-if="hover === i" class="tip">
                  <b class="mono">{{ d.done }}</b> {{ plural(d.done, 'задача', 'задачи', 'задач') }}
                  <div class="muted">{{ formatDate(d.date) }}</div>
                </div>
              </div>
            </div>
          </div>
          <div></div>
          <div class="x-axis mono">
            <span v-for="(d, i) in report.by_day" :key="'x' + d.date" :class="{ show: xLabel(i) }">{{ xLabel(i) ? Number(d.date.slice(8)) : '' }}</span>
          </div>
        </div>
      </div>

      <!-- Команда / личная статистика -->
      <div class="card">
        <div class="row between wrap gap-8" style="margin-bottom: 14px">
          <div>
            <h2 class="h2">{{ auth.isAdmin ? 'Рейтинг команды' : 'Мои задачи за месяц' }}</h2>
            <div class="muted small">Нажмите на строку, чтобы увидеть задачи</div>
          </div>
          <div class="legend small">
            <span><i class="sw ontime"></i> В срок</span>
            <span><i class="sw late"></i> С опозданием</span>
          </div>
        </div>

        <div v-if="!report.people.length" class="empty">
          <div class="empty-ico"><Icon name="users" :size="22" /></div>Нет данных за этот месяц
        </div>

        <div class="people">
          <div v-for="(p, i) in report.people" :key="p.id" class="person" :class="{ open: openId === p.id }">
            <button class="p-row" @click="openId = openId === p.id ? null : p.id">
              <span class="rank mono" :class="'r' + (i + 1)">
                <Icon v-if="i === 0 && p.done" name="trophy" :size="15" />
                <template v-else>{{ i + 1 }}</template>
              </span>
              <span class="avatar sm">{{ initials(p.name) }}</span>
              <span class="p-name">
                <b class="ellipsis">{{ p.name }}</b>
                <span class="muted small">{{ p.roles?.includes('admin') && !p.roles?.includes('worker') ? 'админ' : '@' + p.username }}</span>
              </span>
              <span class="p-bar" :aria-label="`${p.on_time} в срок, ${p.late} с опозданием`">
                <span class="stack">
                  <span v-if="p.on_time" class="seg ontime" :style="{ width: (p.on_time / maxDone * 100) + '%' }"></span>
                  <span v-if="p.late" class="seg late" :style="{ width: (p.late / maxDone * 100) + '%' }"></span>
                </span>
                <b class="mono done-num">{{ p.done }}</b>
              </span>
              <span class="p-stats small">
                <span title="Выполнено в срок"><Icon name="clock" :size="13" /> {{ p.on_time_rate === null ? '—' : p.on_time_rate + '%' }}</span>
                <span :class="{ bad: p.overdue }" title="Просрочено"><Icon name="alert" :size="13" /> {{ p.overdue }}</span>
                <span title="Подзадач закрыто"><Icon name="list-checks" :size="13" /> {{ p.subtasks_done }}</span>
                <span title="Среднее время выполнения"><Icon name="zap" :size="13" /> {{ p.avg_days === null ? '—' : p.avg_days + ' дн.' }}</span>
              </span>
              <Icon name="chevron-down" :size="16" class="chev" />
            </button>

            <div v-if="openId === p.id" class="p-detail">
              <div v-if="!p.done_tasks.length && !p.overdue_tasks.length" class="muted small">Задач за месяц нет.</div>
              <div v-if="p.overdue_tasks.length" class="tlist">
                <div class="tl-title bad"><Icon name="alert" :size="14" /> Просрочено ({{ p.overdue_tasks.length }})</div>
                <div v-for="tk in p.overdue_tasks" :key="tk.id" class="tl-item">
                  <span class="grow ellipsis">{{ tk.title }}</span>
                  <span v-if="tk.project" class="muted small ellipsis hide-xs">{{ tk.project }}</span>
                  <span class="badge red">до {{ formatDate(tk.deadline).slice(0, 5) }}</span>
                </div>
              </div>
              <div v-if="p.done_tasks.length" class="tlist">
                <div class="tl-title"><Icon name="check-circle" :size="14" /> Выполнено ({{ p.done_tasks.length }})</div>
                <div v-for="tk in p.done_tasks" :key="tk.id" class="tl-item">
                  <span class="grow ellipsis">{{ tk.title }}</span>
                  <span v-if="tk.project" class="muted small ellipsis hide-xs">{{ tk.project }}</span>
                  <span class="badge" :class="tk.state === 'late' ? 'amber' : 'green'">
                    {{ formatDate(tk.completed).slice(0, 5) }}{{ tk.state === 'late' ? ' · поздно' : '' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <div v-else class="card empty"><span class="spinner" style="border-color: var(--stroke-strong); border-top-color: var(--brand)"></span>Загрузка отчёта…</div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import api, { formatDate } from '../api'
import { useAuth } from '../stores/auth'
import Icon from '../components/Icon.vue'
import StatCard from '../components/StatCard.vue'

const auth = useAuth()
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

const now = new Date()
const todayIso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
const month = ref(todayIso.slice(0, 7))
const report = ref(null)
const hover = ref(null)
const openId = ref(null)

const t = computed(() => report.value?.totals || {})
const isCurrent = computed(() => month.value >= todayIso.slice(0, 7))
const monthTitle = computed(() => {
  const [y, m] = month.value.split('-').map(Number)
  return `${MONTHS[m - 1]} ${y}`
})

function shift(delta) {
  const [y, m] = month.value.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  month.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

async function load() {
  report.value = null
  hover.value = null
  const { data } = await api.get('/tasks/report/', { params: { month: month.value } })
  report.value = data
  // рабочему сразу показываем его задачи
  openId.value = !auth.isAdmin && data.people[0] ? data.people[0].id : null
}
watch(month, load)
onMounted(load)

// ось Y: «чистые» целые деления
const yMax = computed(() => {
  const max = Math.max(0, ...(report.value?.by_day || []).map(d => d.done))
  if (max <= 4) return 4
  const step = Math.ceil(max / 4)
  return step * 4
})
const yTicks = computed(() => [0, 1, 2, 3, 4].map(i => (yMax.value / 4) * i))
const best = computed(() => {
  const days = report.value?.by_day || []
  const top = days.reduce((a, d) => (d.done > (a?.done || 0) ? d : a), null)
  return top
})
function xLabel(i) {
  const n = report.value.by_day.length
  // 1, 5, 10, … и последний день; без деления, налезающего на последний
  return i === 0 || i === n - 1 || ((i + 1) % 5 === 0 && n - 1 - i >= 3)
}
const maxDone = computed(() => Math.max(1, ...(report.value?.people || []).map(p => p.done)))

function initials(name = '') {
  return name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase()
}
function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100
  if (m10 === 1 && m100 !== 11) return one
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few
  return many
}

// Экспорт: CSV с «;» и BOM — корректно открывается в Excel с кириллицей
function exportCsv() {
  const r = report.value
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const rows = [
    [`Отчёт по задачам — ${monthTitle.value}`],
    [],
    ['Сотрудник', 'Выполнено', 'В срок', 'С опозданием', 'В срок, %', 'Просрочено', 'В работе сейчас', 'Подзадач закрыто', 'Среднее время, дн.'],
    ...r.people.map(p => [p.name, p.done, p.on_time, p.late, p.on_time_rate ?? '', p.overdue, p.in_work, p.subtasks_done, p.avg_days ?? '']),
    ['Итого', t.value.done, t.value.on_time, t.value.late, t.value.on_time_rate ?? '', t.value.overdue, t.value.in_work, t.value.subtasks_done, ''],
    [],
    ['Сотрудник', 'Задача', 'Проект', 'Дедлайн', 'Выполнена', 'Статус'],
    ...r.people.flatMap(p => [
      ...p.done_tasks.map(tk => [p.name, tk.title, tk.project, formatDate(tk.deadline), formatDate(tk.completed), tk.state === 'late' ? 'С опозданием' : 'В срок']),
      ...p.overdue_tasks.map(tk => [p.name, tk.title, tk.project, formatDate(tk.deadline), '', 'Просрочена']),
    ]),
  ]
  const csv = '﻿' + rows.map(row => row.map(esc).join(';')).join('\r\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: `otchet-zadachi-${month.value}.csv` })
  a.click()
  URL.revokeObjectURL(url)
}
function print() {
  // в печать — с раскрытыми списками задач
  window.print()
}
</script>

<style scoped>
.analytics { display: flex; flex-direction: column; gap: 16px; }
.head-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.month-nav { display: flex; align-items: center; gap: 8px; }
.month-label { min-width: 150px; text-align: center; }
.month-label b { font-size: 18px; letter-spacing: -.01em; }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }

/* --- столбчатая диаграмма --- */
.chart { display: grid; grid-template-columns: 28px 1fr; grid-template-rows: 200px auto; gap: 6px 8px; margin-top: 18px; }
.y-axis { position: relative; font-size: 11px; color: var(--muted-2); }
.y-axis span { position: absolute; right: 0; transform: translateY(50%); }
.plot { position: relative; }
.gridline { position: absolute; left: 0; right: 0; height: 1px; background: var(--stroke); }
.bars { position: absolute; inset: 0; display: flex; align-items: flex-end; gap: 2px; }
.bar-slot { position: relative; flex: 1; height: 100%; display: flex; align-items: flex-end; justify-content: center; cursor: pointer; }
.bar-slot:hover, .bar-slot.active { background: var(--hover); border-radius: 6px 6px 0 0; }
.bar { width: 100%; max-width: 24px; min-height: 0; background: var(--c-blue); border-radius: 4px 4px 0 0; transition: height .5s cubic-bezier(.16,1,.3,1); }
.bar-slot.today .bar { background: var(--accent); }
.tip {
  position: absolute; top: -4px; left: 50%; transform: translate(-50%, -100%); z-index: 5; white-space: nowrap;
  background: var(--panel-solid); border: 1px solid var(--stroke-strong); border-radius: 10px; padding: 7px 10px;
  font-size: 12px; box-shadow: var(--shadow); pointer-events: none;
}
.x-axis { display: flex; gap: 2px; font-size: 11px; color: var(--muted-2); }
.x-axis span { flex: 1; text-align: center; }

/* --- рейтинг --- */
.legend { display: flex; gap: 14px; color: var(--muted); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
.sw.ontime, .seg.ontime { background: #059669; }
.sw.late, .seg.late { background: #d97706; }
.people { display: flex; flex-direction: column; gap: 6px; }
.person { border: 1px solid var(--stroke); border-radius: 14px; transition: border-color .2s, background .2s; }
.person.open { border-color: var(--stroke-strong); background: var(--card-2); }
.p-row {
  width: 100%; display: grid; grid-template-columns: 28px 30px minmax(120px, 1.1fr) minmax(140px, 1.4fr) auto 18px;
  align-items: center; gap: 12px; padding: 10px 12px; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer;
}
.rank { width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center; font-size: 12px; background: var(--neutral-bg); color: var(--muted); }
.rank.r1 { background: var(--warn-bg); color: var(--warn-fg); }
.p-name { display: flex; flex-direction: column; min-width: 0; }
.p-bar { display: flex; align-items: center; gap: 10px; }
.stack { flex: 1; display: flex; gap: 2px; height: 12px; }
.seg { height: 100%; border-radius: 0; }
.seg:first-child { border-radius: 4px 0 0 4px; }
.seg:last-child { border-radius: 0 4px 4px 0; }
.seg:only-child { border-radius: 4px; }
.done-num { min-width: 22px; text-align: right; font-size: 16px; }
.p-stats { display: flex; gap: 14px; color: var(--muted); }
.p-stats span { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.p-stats .bad { color: var(--bad-fg); }
.chev { color: var(--muted-2); transition: transform .3s; }
.person.open .chev { transform: rotate(180deg); }
.p-detail { padding: 4px 14px 14px; display: flex; flex-direction: column; gap: 12px; }
.tlist { display: flex; flex-direction: column; gap: 4px; }
.tl-title { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 2px; }
.tl-title.bad { color: var(--bad-fg); }
.tl-item { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 10px; background: var(--card); border: 1px solid var(--stroke); font-size: 14px; }
.tl-item .small { max-width: 30%; }

@media (max-width: 1100px) { .kpis { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 900px) {
  .head-row { flex-direction: column; align-items: stretch; }
  .month-nav { justify-content: space-between; }
  .chart { grid-template-rows: 160px auto; grid-template-columns: 22px 1fr; }
  .bars, .x-axis { gap: 1px; }
  .p-row { grid-template-columns: 26px 30px 1fr auto; row-gap: 8px; }
  .p-bar { grid-column: 1 / -1; grid-row: 2; }
  .p-stats { grid-column: 1 / -1; grid-row: 3; justify-content: space-between; }
  .chev { grid-column: 4; grid-row: 1; }
}
@media (max-width: 480px) {
  .kpis { gap: 10px; }
  .hide-xs { display: none; }
}
@media print {
  .kpis { grid-template-columns: repeat(4, 1fr); }
}
</style>
