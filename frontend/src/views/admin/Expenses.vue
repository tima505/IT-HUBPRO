<template>
  <div class="exp-page">
    <div class="segmented tabs no-print">
      <button :class="{ active: tab === 'list' }" @click="tab = 'list'"><Icon name="wallet" :size="15" /> Расходы</button>
      <button :class="{ active: tab === 'report' }" @click="tab = 'report'"><Icon name="chart" :size="15" /> Отчёт</button>
    </div>

    <!-- ================= Расходы ================= -->
    <div v-if="tab === 'list'" class="exp-grid">
      <form class="card form-card" @submit.prevent="save">
        <div class="row between gap-8">
          <div>
            <div class="eyebrow">{{ editingId ? 'Редактирование' : 'Новый расход' }}</div>
            <h2 class="h2">{{ editingId ? 'Изменить расход' : 'Записать расход' }}</h2>
          </div>
          <button v-if="editingId" type="button" class="btn ghost sm" @click="cancelEdit">Отмена</button>
        </div>

        <div v-if="!editingId && draft.restoredAt.value" class="draft-bar small">
          <Icon name="edit" :size="14" /> <span class="grow">Черновик восстановлен ({{ draftAge(draft.restoredAt.value) }})</span>
          <button type="button" class="btn ghost sm" @click="resetForm">Очистить</button>
        </div>

        <div class="field">
          <label>Сумма</label>
          <MoneyInput v-model="form.amount" size="lg" placeholder="50 000" />
        </div>
        <div class="field">
          <label>Категория</label>
          <div class="cats">
            <button v-for="c in categories" :key="c.value" type="button" class="cat" :class="{ on: form.category === c.value }"
                    @click="form.category = c.value">{{ c.label }}</button>
          </div>
        </div>
        <div class="field">
          <label>На что потрачено</label>
          <input v-model="form.title" class="input" maxlength="200" placeholder="Аренда офиса за октябрь" />
        </div>
        <div class="grid-2">
          <div class="field"><label>Дата</label><input v-model="form.date" type="date" class="input" :max="today" /></div>
          <div class="field">
            <label>Проект <span class="muted">(необязательно)</span></label>
            <select v-model="form.project" class="select input">
              <option :value="null">— без проекта —</option>
              <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label>Из какого фонда</label>
          <PayerPicker fund-only paid-by="company" v-model:paid-from="form.paid_from"
                       :amount="form.amount ? form.amount - refund : null" :buckets="buckets" />
        </div>
        <div class="field">
          <label>Комментарий</label>
          <input v-model="form.note" class="input" maxlength="255" placeholder="Номер счёта, кто оплатил…" />
        </div>
        <div v-if="error" class="badge red err">{{ error }}</div>
        <button class="btn primary block" :disabled="busy || !form.amount || !form.title.trim()">
          <span v-if="busy" class="spinner"></span>
          <template v-else><Icon name="check" :size="17" /> {{ editingId ? 'Сохранить' : 'Записать расход' }}</template>
        </button>
      </form>

      <section class="list-col">
        <div class="filters">
          <div class="segmented">
            <button v-for="p in PRESETS" :key="p.key" :class="{ active: preset === p.key }" @click="preset = p.key">{{ p.label }}</button>
          </div>
          <select v-model="fCategory" class="select input f-sel">
            <option value="">Все категории</option>
            <option v-for="c in categories" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
          <select v-model="fFund" class="select input f-sel">
            <option value="">Все фонды</option>
            <option v-for="b in buckets" :key="b.key" :value="b.key">{{ b.name }}</option>
          </select>
        </div>

        <div class="total card tight">
          <span class="muted">Расходов за период: <b>{{ list.length }}</b></span>
          <b class="mono total-sum">{{ money(listTotal) }}</b>
        </div>

        <transition-group name="list" tag="div" class="rows">
          <article v-for="e in list" :key="e.id" class="exp" :class="{ editing: editingId === e.id }">
            <span class="cat-dot" :class="e.category"><Icon :name="catIcon[e.category] || 'wallet'" :size="16" /></span>
            <div class="grow e-main">
              <b class="ellipsis">{{ e.title }}</b>
              <span class="muted small">
                {{ formatDate(e.date) }} · {{ e.category_display }} · из «{{ bucketName(e.paid_from) }}»
                <template v-if="e.project_name"> · {{ e.project_name }}</template>
              </span>
              <span v-if="e.note" class="muted small ellipsis">{{ e.note }}</span>
            </div>
            <b class="mono e-sum">−{{ money(e.amount) }}</b>
            <div class="e-act">
              <button class="btn ghost sm icon-btn" title="Изменить" @click="startEdit(e)"><Icon name="edit" :size="14" /></button>
              <button class="btn ghost sm icon-btn del" title="Удалить" @click="remove(e)"><Icon name="trash" :size="14" /></button>
            </div>
          </article>
        </transition-group>
        <div v-if="loaded && !list.length" class="card empty">
          <div class="empty-ico"><Icon name="wallet" :size="22" /></div>
          За этот период расходов нет
        </div>
      </section>
    </div>

    <!-- ================= Отчёт ================= -->
    <div v-else class="report">
      <div class="r-head">
        <div class="segmented no-print">
          <button v-for="p in PRESETS" :key="p.key" :class="{ active: rPreset === p.key }" @click="rPreset = p.key">{{ p.label }}</button>
          <button :class="{ active: rPreset === 'custom' }" @click="rPreset = 'custom'">Период…</button>
        </div>
        <div v-if="rPreset === 'custom'" class="row gap-8 no-print">
          <input v-model="rFrom" type="date" class="input d" /> — <input v-model="rTo" type="date" class="input d" :max="today" />
        </div>
        <div class="row gap-8 no-print r-actions">
          <button class="btn sm" :disabled="!report" @click="exportCsv"><Icon name="download" :size="15" /> Excel (CSV)</button>
          <button class="btn sm ghost" @click="print"><Icon name="printer" :size="15" /> Печать</button>
        </div>
      </div>

      <template v-if="report">
        <h2 class="h2 print-title">Отчёт по расходам · {{ formatDate(report.from) }} — {{ formatDate(report.to) }}</h2>
        <div class="kpis">
          <div class="card kpi main">
            <span class="muted small">Всего расходов</span>
            <b class="mono">{{ money(report.total) }}</b>
            <span class="muted small">{{ report.count }} {{ plural(report.count, 'запись', 'записи', 'записей') }}</span>
          </div>
          <div v-for="f in fundRows" :key="f.key" class="card kpi">
            <span class="muted small">Из «{{ f.name }}»</span>
            <b class="mono">{{ money(f.amount) }}</b>
            <span class="muted small">{{ pct(f.amount) }}% расходов</span>
          </div>
        </div>

        <div class="r-grid">
          <div class="card">
            <h3 class="h2 sm">По категориям</h3>
            <div v-if="!report.by_category.length" class="muted small mt-8">Расходов нет</div>
            <div class="bars">
              <div v-for="c in report.by_category" :key="c.key" class="hbar">
                <div class="row between small"><span>{{ c.label }} <span class="muted">· {{ c.count }}</span></span><b class="mono">{{ money(c.amount) }}</b></div>
                <div class="track"><span :style="{ width: (c.amount / maxCat * 100) + '%' }"></span></div>
              </div>
            </div>
          </div>

          <div class="card">
            <h3 class="h2 sm">По месяцам</h3>
            <div class="months">
              <div v-for="m in report.by_month" :key="m.month" class="mcol" :title="`${monthName(m.month)}: ${money(m.amount)}`">
                <span class="mval mono small">{{ m.amount ? short(m.amount) : '' }}</span>
                <div class="mbar-wrap"><div class="mbar" :style="{ height: (m.amount / maxMonth * 100) + '%' }"></div></div>
                <span class="muted small">{{ monthName(m.month, true) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <h3 class="h2 sm">Все расходы за период</h3>
          <div class="table-wrap">
            <table class="table">
              <thead><tr><th>Дата</th><th>На что</th><th>Категория</th><th>Фонд</th><th>Проект</th><th class="ta-r">Сумма</th></tr></thead>
              <tbody>
                <tr v-for="r in report.rows" :key="r.id">
                  <td class="muted mono">{{ formatDate(r.date) }}</td>
                  <td><b>{{ r.title }}</b><div v-if="r.note" class="muted small">{{ r.note }}</div></td>
                  <td><span class="badge gray">{{ r.category_display }}</span></td>
                  <td class="muted">{{ bucketName(r.paid_from) }}</td>
                  <td class="muted">{{ r.project_name || '—' }}</td>
                  <td class="ta-r mono"><b>{{ money(r.amount) }}</b></td>
                </tr>
                <tr v-if="!report.rows.length"><td colspan="6" class="muted center" style="padding: 24px">Расходов за период нет</td></tr>
              </tbody>
              <tfoot v-if="report.rows.length"><tr><td colspan="5"><b>Итого</b></td><td class="ta-r mono"><b>{{ money(report.total) }}</b></td></tr></tfoot>
            </table>
          </div>
        </div>

        <div v-if="report.client_paid.length" class="card">
          <h3 class="h2 sm">Оплачено клиентами <span class="muted small">— не входит в расходы компании</span></h3>
          <div class="client-rows">
            <div v-for="r in report.client_paid" :key="r.id" class="row between small cl">
              <span>{{ formatDate(r.date) }} · {{ r.title }}<span v-if="r.project_name" class="muted"> · {{ r.project_name }}</span></span>
              <b class="mono">{{ money(r.amount) }}</b>
            </div>
          </div>
        </div>
      </template>
      <div v-else class="card empty"><span class="spinner" style="border-color: var(--stroke-strong); border-top-color: var(--brand)"></span>Загрузка отчёта…</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import api, { money, formatDate, errorMessage } from '../../api'
import Icon from '../../components/Icon.vue'
import MoneyInput from '../../components/MoneyInput.vue'
import PayerPicker from '../../components/PayerPicker.vue'
import { useDraft, draftAge } from '../../composables/useDraft'

const emit = defineEmits(['changed'])
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const now = new Date()
const today = iso(now)
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

const tab = ref('list')
const categories = ref([])
const catIcon = { office: 'briefcase', salary: 'users', marketing: 'trending-up', services: 'server', equipment: 'smartphone', taxes: 'bank', other: 'wallet' }
const projects = ref([])
const settings = ref({ fund1_name: 'Фонд 20%', fund2_name: 'Фонд 5%' })
const finance = ref(null)
const buckets = computed(() => [
  { key: 'company', name: 'Деньги компании', balance: finance.value ? Number(finance.value.company.balance) : null },
  { key: 'fund20', name: settings.value.fund1_name, balance: finance.value ? Number(finance.value.fund20.balance) : null },
  { key: 'fund5', name: settings.value.fund2_name, balance: finance.value ? Number(finance.value.fund5.balance) : null },
])
const bucketName = (k) => buckets.value.find(b => b.key === k)?.name || k

// ---------- периоды ----------
function presetRange(key) {
  const y = now.getFullYear(), m = now.getMonth()
  if (key === 'month') return [iso(new Date(y, m, 1)), today]
  if (key === 'prev') return [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))]
  if (key === 'quarter') return [iso(new Date(y, m - 2, 1)), today]
  if (key === 'year') return [iso(new Date(y, 0, 1)), today]
  return [null, null]
}
const PRESETS = [
  { key: 'month', label: 'Этот месяц' }, { key: 'prev', label: 'Прошлый' },
  { key: 'quarter', label: '3 месяца' }, { key: 'year', label: 'Год' },
]

// ---------- форма ----------
const blank = () => ({ amount: null, category: 'other', title: '', note: '', date: today, paid_from: 'company', project: null })
const form = reactive(blank())
const editingId = ref(null)
// пока редактируется существующий расход, черновик нового не трогаем
const draft = useDraft('expense:new', form, { when: () => !editingId.value })
const editingOrig = ref(null)
const busy = ref(false)
const error = ref('')
// при редактировании старая сумма возвращается в тот же фонд — для подсказки о нехватке
const refund = computed(() => (editingOrig.value && editingOrig.value.paid_from === form.paid_from ? Number(editingOrig.value.amount) : 0))

async function save() {
  error.value = ''
  busy.value = true
  const payload = { ...form, title: form.title.trim() }
  try {
    if (editingId.value) await api.patch(`/expenses/${editingId.value}/`, payload, { silentError: true })
    else await api.post('/expenses/', payload, { silentError: true })
    if (!editingId.value) draft.clear()
    editingId.value = null
    editingOrig.value = null
    Object.assign(form, blank())
    await Promise.all([loadList(), loadFinance()])
    emit('changed')
  } catch (e) { error.value = errorMessage(e) } finally { busy.value = false }
}
let draftBeforeEdit = null
function startEdit(e) {
  if (!editingId.value) draftBeforeEdit = { ...form }   // черновик нового расхода не теряем
  editingId.value = e.id
  editingOrig.value = e
  error.value = ''
  Object.assign(form, { amount: Number(e.amount), category: e.category, title: e.title, note: e.note,
    date: e.date, paid_from: e.paid_from, project: e.project })
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
function cancelEdit() {
  editingId.value = null
  editingOrig.value = null
  Object.assign(form, draftBeforeEdit || blank())
}
function resetForm() { draft.clear(); Object.assign(form, blank()) }
async function remove(e) {
  if (!confirm(`Удалить расход «${e.title}» на ${money(e.amount)}? Деньги вернутся в «${bucketName(e.paid_from)}».`)) return
  await api.delete(`/expenses/${e.id}/`)
  if (editingId.value === e.id) cancelEdit()
  await Promise.all([loadList(), loadFinance()])
  emit('changed')
}

// ---------- список ----------
const preset = ref('month')
const fCategory = ref('')
const fFund = ref('')
const list = ref([])
const loaded = ref(false)
const listTotal = computed(() => list.value.reduce((a, e) => a + Number(e.amount), 0))
async function loadList() {
  const [from, to] = presetRange(preset.value)
  const params = { from, to, category: fCategory.value || undefined, paid_from: fFund.value || undefined }
  list.value = (await api.get('/expenses/', { params })).data
  loaded.value = true
}
watch([preset, fCategory, fFund], loadList)
async function loadFinance() { finance.value = (await api.get('/finance/')).data }

// ---------- отчёт ----------
const rPreset = ref('month')
const rFrom = ref(presetRange('month')[0])
const rTo = ref(today)
const report = ref(null)
async function loadReport() {
  const [from, to] = rPreset.value === 'custom' ? [rFrom.value, rTo.value] : presetRange(rPreset.value)
  if (!from || !to) return
  report.value = null
  report.value = (await api.get('/expenses/report/', { params: { from, to } })).data
}
watch([rPreset, rFrom, rTo], loadReport)
watch(tab, (t) => { if (t === 'report') loadReport() })

const fundRows = computed(() => buckets.value.map(b => ({
  ...b, amount: Number(report.value?.by_fund.find(f => f.key === b.key)?.amount || 0),
})))
const maxCat = computed(() => Math.max(1, ...(report.value?.by_category || []).map(c => Number(c.amount))))
const maxMonth = computed(() => Math.max(1, ...(report.value?.by_month || []).map(m => Number(m.amount))))
const pct = (v) => (Number(report.value?.total) ? Math.round(Number(v) * 100 / Number(report.value.total)) : 0)
function monthName(key, shortName = false) {
  const [y, m] = key.split('-').map(Number)
  return shortName ? MONTHS[m - 1].slice(0, 3) : `${MONTHS[m - 1]} ${y}`
}
const short = (v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}М` : v >= 1e3 ? `${Math.round(v / 1e3)}К` : String(v))
function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100
  if (m10 === 1 && m100 !== 11) return one
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few
  return many
}

function exportCsv() {
  const r = report.value
  const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const rows = [
    [`Отчёт по расходам ${formatDate(r.from)} — ${formatDate(r.to)}`],
    [],
    ['Дата', 'На что', 'Категория', 'Фонд', 'Проект', 'Комментарий', 'Сумма'],
    ...r.rows.map(x => [formatDate(x.date), x.title, x.category_display, bucketName(x.paid_from), x.project_name, x.note, x.amount]),
    ['', '', '', '', '', 'Итого', r.total],
    [],
    ['По категориям'],
    ...r.by_category.map(c => [c.label, c.count, c.amount]),
    [],
    ['По фондам'],
    ...fundRows.value.map(f => [f.name, f.amount]),
  ]
  if (r.client_paid.length) {
    rows.push([], ['Оплачено клиентами (не входит в расходы)'], ...r.client_paid.map(x => [formatDate(x.date), x.title, x.project_name, x.amount]))
  }
  const csv = '﻿' + rows.map(row => row.map(esc).join(';')).join('\r\n')
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  Object.assign(document.createElement('a'), { href: url, download: `rashody-${r.from}-${r.to}.csv` }).click()
  URL.revokeObjectURL(url)
}
function print() { window.print() }

onMounted(async () => {
  const [c, p, s] = await Promise.all([api.get('/expenses/categories/'), api.get('/projects/'), api.get('/settings/')])
  categories.value = c.data
  projects.value = p.data
  settings.value = s.data
  draft.restore()
  await Promise.all([loadList(), loadFinance()])
})
</script>

<style scoped>
.exp-page { display: flex; flex-direction: column; gap: 16px; }
.tabs { align-self: flex-start; }
.tabs button { display: inline-flex; align-items: center; gap: 6px; }
.exp-grid { display: grid; grid-template-columns: 420px 1fr; gap: 16px; align-items: start; }
.form-card { display: flex; flex-direction: column; gap: 14px; position: sticky; top: 96px; }
.draft-bar { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 12px; background: var(--info-bg); }
.cats { display: flex; flex-wrap: wrap; gap: 6px; }
.cat { border: 1px solid var(--stroke); background: var(--card-2); color: var(--muted); font: 600 12.5px var(--font);
  padding: 6px 11px; border-radius: 99px; cursor: pointer; transition: all .2s; }
.cat:hover { color: var(--text); }
.cat.on { background: var(--brand); border-color: var(--brand); color: #fff; }
.err { white-space: normal; }

.list-col { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filters .segmented { overflow-x: auto; scrollbar-width: none; max-width: 100%; }
.f-sel { width: auto; flex: 1 1 160px; }
.total { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.total-sum { font-size: 20px; color: var(--bad-fg); }
.rows { display: flex; flex-direction: column; gap: 8px; position: relative; }
.exp { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 14px; background: var(--card);
  border: 1px solid var(--stroke); transition: border-color .2s; }
.exp:hover { border-color: var(--stroke-strong); }
.exp.editing { border-color: var(--brand); }
.e-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.e-sum { white-space: nowrap; font-size: 15px; }
.e-act { display: flex; gap: 2px; }
.e-act .del:hover { color: var(--bad-fg); }
.cat-dot { width: 36px; height: 36px; border-radius: 11px; display: grid; place-items: center; flex-shrink: 0;
  background: var(--neutral-bg); color: var(--muted); }

.report { display: flex; flex-direction: column; gap: 16px; }
.r-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.r-head .segmented { overflow-x: auto; scrollbar-width: none; max-width: 100%; }
.r-actions { margin-left: auto; }
.d { width: 150px; }
.print-title { display: none; }
.kpis { display: grid; grid-template-columns: 1.3fr 1fr 1fr 1fr; gap: 12px; }
.kpi { display: flex; flex-direction: column; gap: 4px; padding: 16px; }
.kpi b { font-size: 20px; letter-spacing: -.02em; }
.kpi.main b { font-size: 26px; color: var(--bad-fg); }
.r-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.h2.sm { font-size: 16px; }
.bars { display: flex; flex-direction: column; gap: 12px; margin-top: 14px; }
.hbar { display: flex; flex-direction: column; gap: 6px; }
.track { height: 10px; border-radius: 0 4px 4px 0; background: var(--neutral-bg); }
.track span { display: block; height: 100%; border-radius: 0 4px 4px 0; background: var(--c-blue); }
.months { display: flex; align-items: flex-end; gap: 6px; height: 190px; margin-top: 14px; }
.mcol { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; height: 100%; min-width: 0; }
.mbar-wrap { flex: 1; width: 100%; display: flex; align-items: flex-end; justify-content: center; border-bottom: 1px solid var(--stroke); }
.mbar { width: 100%; max-width: 24px; background: var(--c-blue); border-radius: 4px 4px 0 0; min-height: 0; }
.mval { color: var(--muted); height: 16px; }
.table-wrap { overflow-x: auto; margin-top: 10px; }
.ta-r { text-align: right; }
tfoot td { padding: 14px; border-top: 1px solid var(--stroke-strong); }
.client-rows { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
.cl { padding: 8px 10px; border-radius: 10px; background: var(--card-2); gap: 10px; }

@media (max-width: 1100px) {
  .exp-grid { grid-template-columns: 1fr; }
  .form-card { position: static; }
  .kpis { grid-template-columns: 1fr 1fr; }
  .r-grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .exp { flex-wrap: wrap; }
  .e-main { flex-basis: calc(100% - 60px); }
  .e-sum { margin-left: 48px; }
  .e-act { margin-left: auto; }
  .r-actions { margin-left: 0; }
  .kpis { grid-template-columns: 1fr; }
}
@media print {
  .print-title { display: block; }
  .kpis { grid-template-columns: repeat(4, 1fr); }
  .r-grid { grid-template-columns: 1fr 1fr; }
}
</style>
