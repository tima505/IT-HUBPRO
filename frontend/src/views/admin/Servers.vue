<template>
  <div>
    <div class="row between" style="margin-bottom: 20px">
      <p class="muted">Управление серверами: покупка, продление, история и учёт оплаты из фондов.</p>
      <button class="btn primary" @click="openBuy"><Icon name="server" :size="18" /> Купить сервер</button>
    </div>

    <FilterBar v-model:search="q" v-model:from="dateFrom" v-model:to="dateTo" dates date-label="Действует до"
      placeholder="Сервер, проект, логин…" :count="shown.length" :total="servers.length"
      :extra-active="!!state" @reset="state = ''">
      <select v-model="state" class="select f-select">
        <option value="">Любой срок</option>
        <option value="soon">Истекают за 7 дней</option>
        <option value="expired">Истёкшие</option>
        <option value="ok">Активные</option>
      </select>
    </FilterBar>

    <div class="card tight">
      <table class="table">
        <thead>
          <tr><th>Сервер</th><th>Логин</th><th>Проект</th><th>Действует до</th><th>Осталось</th><th>Стоимость</th><th>Кто платил</th><th style="width:1%"></th></tr>
        </thead>
        <tbody>
          <tr v-for="s in shown" :key="s.id">
            <td><b>{{ s.label }}</b></td>
            <td class="muted mono">{{ s.login }}</td>
            <td class="muted">{{ s.project_name || '—' }}</td>
            <td class="muted">{{ formatDate(s.expiry_date) }}</td>
            <td>
              <span class="badge" :class="s.days_left <= 1 ? 'red pulse' : (s.days_left <= 7 ? 'amber' : 'green')">
                {{ s.days_left < 0 ? 'истёк' : `${s.days_left} дн.` }}
              </span>
            </td>
            <td class="mono">{{ money(s.amount) }}</td>
            <td><span v-if="s.paid_by === 'client'" class="badge blue">Клиент</span><span v-else>{{ bucketName(s.paid_from) }}</span></td>
            <td>
              <div class="row gap-8" style="justify-content: flex-end; white-space: nowrap">
                <button class="btn sm green" @click="openRenew(s)"><Icon name="renew" :size="15" /> Продлить</button>
                <button class="btn sm ghost icon-only" title="История и доступы" @click="openHistory(s)"><Icon name="clock" :size="16" /></button>
                <button class="btn sm ghost icon-only" title="Редактировать" @click="openEdit(s)"><Icon name="edit" :size="16" /></button>
                <button class="btn sm danger icon-only" title="Удалить" @click="openDelete(s)"><Icon name="close" :size="16" /></button>
              </div>
            </td>
          </tr>
          <tr v-if="!shown.length"><td colspan="8" class="muted center" style="padding: 30px">{{ servers.length ? 'По фильтрам ничего не найдено' : 'Серверов нет' }}</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Купить -->
    <Modal v-model="buyModal" eyebrow="Инфраструктура" title="Покупка сервера">
      <div class="grid-2">
        <div class="field"><label>Название / назначение</label><input v-model="b.label" class="input" placeholder="VPS для проекта" /></div>
        <div class="field">
          <label>Проект (необязательно)</label>
          <select v-model="b.project" class="select">
            <option :value="null">— без привязки —</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
      </div>
      <div class="grid-2">
        <div class="field"><label>Логин</label><input v-model="b.login" class="input" placeholder="root" /></div>
        <div class="field"><label>Пароль</label><input v-model="b.password" class="input" placeholder="••••••" /></div>
      </div>
      <div class="grid-2">
        <div class="field"><label>Когда куплен</label><input v-model="b.purchase_date" type="date" class="input" :max="today" /></div>
        <div class="field"><label>Стоимость</label><MoneyInput v-model="b.amount" placeholder="45 000" /></div>
      </div>
      <div class="field">
        <label>На какой срок</label>
        <TermPicker v-model:months="b.months" v-model:days="b.days" :start="b.purchase_date" />
      </div>
      <div class="field">
        <label>Кто платит</label>
        <PayerPicker v-model:paid-by="b.paid_by" v-model:paid-from="b.paid_from" :amount="b.amount" :buckets="buckets" />
      </div>
      <div v-if="formError" class="badge red mt-8">{{ formError }}</div>
      <div class="row between mt-16">
        <button class="btn ghost" @click="buyModal = false">Отмена</button>
        <button class="btn primary" :disabled="busy || !b.label || (!b.months && !b.days)" @click="buy"><span v-if="busy" class="spinner"></span><span v-else>Купить</span></button>
      </div>
    </Modal>

    <!-- Продлить -->
    <Modal v-model="renewModal" eyebrow="Продление" :title="`Продлить: ${current?.label || ''}`">
      <div class="field">
        <label>Продлить на срок</label>
        <TermPicker v-model:months="r.months" v-model:days="r.days" :start="renewStart" />
      </div>
      <div class="field"><label>Стоимость</label><MoneyInput v-model="r.amount" placeholder="45 000" /></div>
      <div class="field">
        <label>Кто платит</label>
        <PayerPicker v-model:paid-by="r.paid_by" v-model:paid-from="r.paid_from" :amount="r.amount" :buckets="buckets" />
      </div>
      <div v-if="formError" class="badge red mt-8">{{ formError }}</div>
      <div class="row between mt-16">
        <button class="btn ghost" @click="renewModal = false">Отмена</button>
        <button class="btn primary" :disabled="busy || (!r.months && !r.days)" @click="renew"><span v-if="busy" class="spinner"></span><span v-else>Продлить</span></button>
      </div>
    </Modal>

    <!-- История и доступы -->
    <Modal v-model="histModal" class="wide" eyebrow="Сервер" :title="current?.label || ''">
      <div v-if="current">
        <!-- доступы -->
        <div class="access">
          <div class="acc-item">
            <span class="muted small">Логин</span>
            <div class="row between"><b class="mono">{{ current.login || '—' }}</b>
              <button class="btn sm ghost" @click="copy(current.login)">копировать</button></div>
          </div>
          <div class="acc-item">
            <span class="muted small">Пароль</span>
            <div class="row between">
              <b class="mono">{{ showPass ? (current.password || '—') : '••••••••' }}</b>
              <div class="row gap-8">
                <button class="btn sm ghost" @click="showPass = !showPass"><Icon name="eye" :size="15" /> {{ showPass ? 'скрыть' : 'показать' }}</button>
                <button class="btn sm ghost" @click="copy(current.password)">копировать</button>
              </div>
            </div>
          </div>
        </div>

        <h3 class="h2" style="margin: 22px 0 10px">История покупок и продлений</h3>
        <div class="dtable">
          <div class="dt-row dt-head"><span>Событие</span><span>Дата</span><span>Срок</span><span class="ta-r">Стоимость</span><span>Оплачен из</span></div>
          <div class="dt-row">
            <span><b>Покупка</b></span>
            <span class="muted mono">{{ formatDate(current.purchase_date) }}</span>
            <span class="muted">{{ termText(current.months, current.days) }}</span>
            <span class="ta-r mono">{{ money(current.amount) }}</span>
            <span class="muted">{{ current.paid_by === 'client' ? 'Клиент' : bucketName(current.paid_from) }}</span>
          </div>
          <div v-for="rn in current.renewals" :key="rn.id" class="dt-row">
            <span><b>Продление</b> <span class="muted small">до {{ formatDate(rn.new_expiry) }}</span></span>
            <span class="muted mono">{{ formatDate(rn.date) }}</span>
            <span class="muted">+{{ termText(rn.months, rn.days) }}</span>
            <span class="ta-r mono">{{ money(rn.amount) }}</span>
            <span class="muted">{{ rn.paid_by === 'client' ? 'Клиент' : bucketName(rn.paid_from) }}</span>
          </div>
        </div>
        <div class="row between total-row mt-16">
          <b>Всего потрачено компанией</b>
          <b class="mono" style="font-size: 17px">{{ money(totalSpent) }}</b>
        </div>
      </div>
    </Modal>

    <!-- Редактировать -->
    <Modal v-model="editModal" eyebrow="Редактирование" :title="`Изменить: ${current?.label || ''}`">
      <div class="grid-2">
        <div class="field"><label>Название / назначение</label><input v-model="e.label" class="input" /></div>
        <div class="field">
          <label>Проект</label>
          <select v-model="e.project" class="select">
            <option :value="null">— без привязки —</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
      </div>
      <div class="grid-2">
        <div class="field"><label>Логин</label><input v-model="e.login" class="input" /></div>
        <div class="field"><label>Пароль</label><input v-model="e.password" class="input" /></div>
      </div>
      <div class="row between mt-16">
        <button class="btn ghost" @click="editModal = false">Отмена</button>
        <button class="btn primary" :disabled="busy" @click="saveEdit"><span v-if="busy" class="spinner"></span><span v-else>Сохранить</span></button>
      </div>
    </Modal>

    <!-- Удалить -->
    <Modal v-model="delModal" eyebrow="Удаление" title="Удалить сервер?">
      <p class="muted">Сервер <b style="color: var(--text)">«{{ current?.label }}»</b> и вся его история продлений будут удалены безвозвратно.</p>
      <div class="row between mt-16">
        <button class="btn ghost" @click="delModal = false">Отмена</button>
        <button class="btn danger" :disabled="busy" @click="confirmDelete"><span v-if="busy" class="spinner"></span><span v-else>Удалить</span></button>
      </div>
    </Modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api, { money, formatDate, errorMessage } from '../../api'
import Modal from '../../components/Modal.vue'
import Icon from '../../components/Icon.vue'
import FilterBar from '../../components/FilterBar.vue'
import MoneyInput from '../../components/MoneyInput.vue'
import TermPicker from '../../components/TermPicker.vue'
import PayerPicker from '../../components/PayerPicker.vue'
import { textMatch, inRange } from '../../filters'

const emit = defineEmits(['changed'])
const servers = ref([])

// ----- поиск и фильтры -----
const q = ref('')
const state = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const byState = {
  soon: s => s.days_left >= 0 && s.days_left <= 7,
  expired: s => s.days_left < 0,
  ok: s => s.days_left >= 0,
}
const shown = computed(() => servers.value.filter(s =>
  textMatch(q.value, s.label, s.login, s.project_name, s.paid_from_display) &&
  (!state.value || byState[state.value](s)) &&
  inRange(s.expiry_date, dateFrom.value, dateTo.value)
))
const projects = ref([])
const buyModal = ref(false)
const renewModal = ref(false)
const histModal = ref(false)
const editModal = ref(false)
const delModal = ref(false)
const busy = ref(false)
const current = ref(null)
const showPass = ref(false)

const now = new Date()
const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
const blankBuy = () => ({ label: '', project: null, login: '', password: '', purchase_date: today, months: 12, days: null,
  amount: null, paid_by: 'company', paid_from: 'company' })
const b = reactive(blankBuy())
const r = reactive({ months: 12, days: null, amount: null, paid_by: 'company', paid_from: 'company' })
const formError = ref('')
const settings = ref({ fund1_name: 'Фонд 20%', fund2_name: 'Фонд 5%' })
const finance = ref(null)
const buckets = computed(() => [
  { key: 'company', name: 'Деньги компании', balance: finance.value ? Number(finance.value.company.balance) : null },
  { key: 'fund20', name: settings.value.fund1_name, balance: finance.value ? Number(finance.value.fund20.balance) : null },
  { key: 'fund5', name: settings.value.fund2_name, balance: finance.value ? Number(finance.value.fund5.balance) : null },
])
// продление считается от окончания срока (или от сегодня, если сервер уже истёк)
const renewStart = computed(() => {
  const exp = current.value?.expiry_date
  return exp && exp > today ? exp : today
})
function termText(months, days) {
  if (months) return months % 12 === 0 ? (months === 12 ? '1 год' : `${months / 12} г.`) : `${months} мес.`
  return `${days} дн.`
}
const e = reactive({ label: '', project: null, login: '', password: '' })

const bucketName = (k) => buckets.value.find(b => b.key === k)?.name || k

// сколько потратила компания (оплаченное клиентом не считается)
const totalSpent = computed(() => {
  if (!current.value) return 0
  const own = (x) => (x.paid_by === 'client' ? 0 : Number(x.amount || 0))
  return own(current.value) + (current.value.renewals || []).reduce((a, x) => a + own(x), 0)
})

async function loadFinance() { finance.value = (await api.get('/finance/')).data }
function openBuy() { Object.assign(b, blankBuy()); formError.value = ''; buyModal.value = true; loadFinance() }
function openRenew(s) {
  current.value = s
  Object.assign(r, { months: s.months || 12, days: s.months ? null : null, amount: Number(s.amount) || null,
    paid_by: s.paid_by || 'company', paid_from: s.paid_from || 'company' })
  formError.value = ''; renewModal.value = true; loadFinance()
}
function openHistory(s) { current.value = s; showPass.value = false; histModal.value = true }
function openEdit(s) { current.value = s; Object.assign(e, { label: s.label, project: s.project, login: s.login, password: s.password }); editModal.value = true }
function openDelete(s) { current.value = s; delModal.value = true }

function copy(text) { if (text) navigator.clipboard?.writeText(text) }

async function buy() {
  busy.value = true; formError.value = ''
  try {
    await api.post('/servers/', { ...b, amount: b.amount || 0, days: b.months ? null : b.days }, { silentError: true })
    buyModal.value = false; await load(); emit('changed')
  } catch (e) { formError.value = errorMessage(e) } finally { busy.value = false }
}
async function renew() {
  busy.value = true; formError.value = ''
  try {
    await api.post(`/servers/${current.value.id}/renew/`, { ...r, amount: r.amount || 0, days: r.months ? null : r.days }, { silentError: true })
    renewModal.value = false; await load(); emit('changed')
  } catch (e) { formError.value = errorMessage(e) } finally { busy.value = false }
}
async function saveEdit() {
  busy.value = true
  try {
    await api.patch(`/servers/${current.value.id}/`, { ...e })
    editModal.value = false; await load(); emit('changed')
  } finally { busy.value = false }
}
async function confirmDelete() {
  busy.value = true
  try {
    await api.delete(`/servers/${current.value.id}/`)
    delModal.value = false; await load(); emit('changed')
  } finally { busy.value = false }
}

async function load() {
  const [s, p, st] = await Promise.all([api.get('/servers/'), api.get('/projects/'), api.get('/settings/')])
  servers.value = s.data; projects.value = p.data; settings.value = st.data
}
onMounted(load)
</script>

<style scoped>
.icon-only { padding: 7px 9px; }
.access { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.acc-item { padding: 12px 14px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); }
.acc-item .row { margin-top: 4px; }
.dtable { border: 1px solid var(--stroke); border-radius: 12px; overflow: hidden; }
.dt-row { display: grid; grid-template-columns: 1.8fr 1.1fr .9fr 1.1fr 1.2fr; gap: 10px; padding: 11px 14px; align-items: center; font-size: 14px; border-bottom: 1px solid var(--stroke); }
.dt-row:last-child { border-bottom: none; }
.dt-head { background: var(--input-bg); font-size: 12px; text-transform: uppercase; letter-spacing: .03em; color: var(--muted-2); font-weight: 600; }
.dt-row:not(.dt-head):hover { background: var(--hover); }
.ta-r { text-align: right; }
.total-row { padding: 14px 16px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); }
@media (max-width: 700px) { .access { grid-template-columns: 1fr; } }
</style>
