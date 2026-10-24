<template>
  <div v-if="p">
    <button class="btn ghost sm" @click="$router.push('/projects')" style="margin-bottom: 16px"><Icon name="arrow-left" :size="16" /> К проектам</button>

    <div class="head card animate-in">
      <div class="row between wrap gap-16">
        <div>
          <div class="row gap-8 wrap">
            <StatusBadge :status="p.status" />
            <span v-if="p.has_monthly" class="badge amber">Ежемесячная</span>
            <DeadlineBadge :status="p.deadline_status" />
            <ReviewBadge v-if="p.review_status !== 'none'" :status="p.review_status" />
          </div>
          <h1 class="h1" style="margin-top: 10px">{{ p.name }}</h1>
          <div class="muted mt-8 row gap-8 wrap"><Icon name="user" :size="15" /> Рабочий: <b style="color: var(--text)">{{ p.worker_name || p.worker_username }}</b></div>
          <div class="muted mt-8 row gap-8 wrap">
            <Icon name="phone" :size="15" /> Клиент:
            <b v-if="p.client_name || p.client_phone" style="color: var(--text)">{{ [p.client_name, p.client_phone].filter(Boolean).join(' · ') }}</b>
            <span v-else>не указан</span>
            <button class="btn ghost sm icon-only" title="Изменить данные клиента" style="padding: 4px; height: auto" @click="openClient"><Icon name="edit" :size="14" /></button>
          </div>
        </div>
        <div class="row gap-8 wrap">
          <button v-if="!p.finished_date" class="btn green" @click="finish"><Icon name="check" :size="16" /> Отметить сдачу</button>
          <button v-else class="btn ghost" @click="unfinish"><Icon name="close" :size="15" /> Снять отметку сдачи</button>
          <button v-if="p.status === 'active'" class="btn primary" @click="openComplete"><Icon name="flag" :size="16" /> Завершить проект</button>
        </div>
      </div>

      <div class="dates mt-24">
        <div class="date-chip"><span class="muted small">Начало</span><b>{{ formatDate(p.start_date) }}</b></div>
        <div class="date-chip"><span class="muted small">Дедлайн</span><b>{{ formatDate(p.deadline_date) }}</b></div>
        <div class="date-chip"><span class="muted small">Бета-версия</span><b>{{ formatDate(p.beta_date) }}</b></div>
        <div class="date-chip"><span class="muted small">Сдал рабочий</span><b>{{ p.finished_date ? formatDate(p.finished_date) : '—' }}</b></div>
        <div v-if="p.has_monthly" class="date-chip"><span class="muted small">След. оплата</span><b>{{ formatDate(p.monthly_next_due) }}</b></div>
      </div>
    </div>

    <!-- Оплата за проект: одна сумма, клиент платит частями -->
    <div class="mt-24">
      <h2 class="h2" style="margin-bottom: 12px">Оплата за проект</h2>
      <div v-if="!p.has_price" class="card row between wrap gap-12">
        <span class="muted">Оплата за проект не включена — только ежемесячная.</span>
        <button class="btn sm" @click="patch({ has_price: true })"><Icon name="plus" :size="15" /> Включить оплату за проект</button>
      </div>
      <div v-else class="grid-3">
        <div class="card stage-card animate-in d1">
          <div class="row between mb-8"><b>Сумма проекта</b>
            <span v-if="p.price && paid >= Number(p.price)" class="badge green">Оплачен</span>
          </div>
          <div class="amount mono">{{ p.price ? money(p.price) : 'не указана' }}</div>
          <div class="row gap-8 wrap mt-8">
            <button class="btn sm ghost" @click="openAmount('price', 'set')"><Icon name="edit" :size="14" /> Изменить</button>
            <button class="btn sm ghost" @click="openAmount('price', 'add')"><Icon name="plus" :size="14" /> Добавить</button>
          </div>
        </div>

        <div class="card stage-card animate-in d2">
          <div class="row between mb-8"><b>Оплачено клиентом</b><span class="muted small">{{ projectPayments.length }} опл.</span></div>
          <div class="amount mono">{{ money(paid) }}</div>
          <template v-if="p.price">
            <div class="bar"><div class="bar-fill" :style="{ width: Math.min(100, paid / Number(p.price) * 100) + '%' }"></div></div>
            <div class="muted small">{{ left > 0 ? `Осталось ${money(left)}` : (left < 0 ? `Переплата ${money(-left)}` : 'Оплачено полностью') }}</div>
          </template>
          <button v-if="p.status !== 'cancelled'" class="btn green sm mt-8" @click="openPay"><Icon name="check" :size="14" /> Принять оплату</button>
        </div>

        <div class="card stage-card animate-in d3">
          <div class="row between mb-8"><b>Рабочему</b><span class="muted small">{{ p.worker_name || p.worker_username }}</span></div>
          <div class="amount mono">{{ p.worker_amount ? money(p.worker_amount) : 'не указана' }}</div>
          <div class="muted small">Начислено: <b style="color: var(--text)">{{ money(p.totals.worker) }}</b>
            <template v-if="p.worker_amount"> · осталось {{ money(Math.max(0, Number(p.worker_amount) - Number(p.totals.worker))) }}</template>
          </div>
          <div class="row gap-8 wrap mt-8">
            <button class="btn sm ghost" @click="openAmount('worker_amount', 'set')"><Icon name="edit" :size="14" /> Изменить</button>
            <button class="btn sm ghost" @click="openAmount('worker_amount', 'add')"><Icon name="plus" :size="14" /> Добавить</button>
          </div>
        </div>
      </div>
      <div v-if="p.has_price" class="muted small" style="margin-top: 8px">
        С каждой оплаты клиента рабочий получает свою долю пропорционально: оплатили половину суммы — ему половина его суммы.
        Если сумму проекта или рабочему поменять позже, его доля с уже полученных оплат пересчитается.
      </div>
    </div>

    <!-- Ежемесячная оплата -->
    <div v-if="p.has_monthly" class="mt-24">
      <h2 class="h2" style="margin-bottom: 12px">Ежемесячное обслуживание</h2>
      <div class="card stage-card animate-in d4" style="max-width: 350px">
        <div class="row between mb-8">
          <b>Оплата в месяц</b>
          <span class="badge amber" v-if="p.status === 'active'">Активно</span>
        </div>
        <div class="row between mb-12" style="align-items: center">
          <span class="mono" style="font-size: 18px; font-weight: 700">{{ money(p.monthly_amount) }} / мес</span>
          <button v-if="p.status === 'active'" class="btn ghost icon-only sm" @click="openEditAmount('monthly_amount', p.monthly_amount)" style="padding: 4px; height: auto"><Icon name="edit" :size="14" /></button>
        </div>
        <div class="muted small mb-12" v-if="p.monthly_next_due">
          Следующая оплата: <b>{{ formatDate(p.monthly_next_due) }}</b>
        </div>
        <button v-if="p.status === 'active'" class="btn green sm" @click="payMonthly">
          <Icon name="check" :size="14" /> Провести платёж за месяц
        </button>
        <div v-else class="muted small">Проект завершён</div>
      </div>
    </div>

    <!-- Проверка тестировщиком -->
    <div class="card mt-24 animate-in d2">
      <div class="row between wrap gap-12" style="margin-bottom: 14px">
        <h2 class="h2">Проверка и комментарии</h2>
        <span class="muted small">Проверяет любой тестировщик · решение того, кто ответил первым</span>
      </div>
      <ReviewThread :project="p" @update="onReviewUpdate" />
    </div>

    <!-- Распределение -->
    <div class="grid-5 mt-24">
      <StatCard class="animate-in d1" label="Всего получено" :value="p.totals.received" icon="trending-up" color="#2563eb" />
      <StatCard class="animate-in d2" label="Фонд 20%" :value="p.totals.fund20" icon="percent" color="#4f46e5" />
      <StatCard class="animate-in d3" label="Фонд 5%" :value="p.totals.fund5" icon="percent" color="#0284c7" />
      <StatCard class="animate-in d4" label="Рабочему" :value="p.totals.worker" icon="user" color="#d97706" />
      <StatCard class="animate-in d5" label="Компании" :value="p.totals.company" icon="bank" color="#059669" />
    </div>

    <div class="two-col mt-24">
      <div class="card animate-in d3">
        <h2 class="h2" style="margin-bottom: 12px">История платежей</h2>
        <table class="table">
          <thead><tr><th>Тип</th><th>Дата</th><th>Сумма</th><th>20%</th><th>5%</th><th>Рабочему</th><th>Компании</th></tr></thead>
          <tbody>
            <tr v-for="pay in p.payments" :key="pay.id">
              <td><span class="badge gray">{{ pay.kind_display }}</span></td>
              <td class="muted">{{ formatDate(pay.date) }}</td>
              <td class="mono"><b>{{ money(pay.amount) }}</b></td>
              <td class="mono muted">{{ money(pay.fund20_amount) }}</td>
              <td class="mono muted">{{ money(pay.fund5_amount) }}</td>
              <td class="mono muted">{{ money(pay.worker_amount) }}</td>
              <td class="mono muted">{{ money(pay.company_amount) }}</td>
            </tr>
            <tr v-if="!p.payments.length"><td colspan="7" class="muted center" style="padding: 20px">Платежей пока нет</td></tr>
          </tbody>
        </table>
      </div>

      <div class="card animate-in d4">
        <h2 class="h2" style="margin-bottom: 12px">Серверы проекта</h2>
        <div v-if="!p.servers.length" class="muted small center" style="padding: 24px 0">Серверов нет</div>
        <div v-for="s in p.servers" :key="s.id" class="srv">
          <div class="row between">
            <b>{{ s.label }}</b>
            <span class="badge" :class="s.days_left <= 1 ? 'red pulse' : (s.days_left <= 7 ? 'amber' : 'green')">
              {{ s.days_left < 0 ? 'истёк' : `${s.days_left} дн.` }}
            </span>
          </div>
          <div class="muted small mt-8 row gap-8"><Icon name="key" :size="14" /> {{ s.login }} · до {{ formatDate(s.expiry_date) }} · {{ money(s.amount) }}</div>
        </div>
      </div>
    </div>

    <Modal v-model="payModal" eyebrow="Платёж" title="Принять оплату">
      <div class="field">
        <label>Сумма, ₸</label>
        <input v-model="payAmount" type="number" min="0" class="input" autofocus />
        <span v-if="p.price && left > 0" class="muted small">Осталось по проекту: {{ money(left) }}</span>
      </div>
      <transition name="pop"><div v-if="modalError" class="badge red" style="margin-top: 8px">{{ modalError }}</div></transition>
      <div class="row between mt-16">
        <button class="btn ghost" @click="payModal = false">Отмена</button>
        <button class="btn primary" :disabled="busy || !(Number(payAmount) > 0)" @click="doPay"><span v-if="busy" class="spinner"></span><span v-else>Провести</span></button>
      </div>
    </Modal>

    <Modal v-model="completeModal" eyebrow="Проект" title="Завершить проект?">
      <div class="muted">Проект будет переведён в статус «Завершён».</div>
      <div class="row between mt-16">
        <button class="btn ghost" @click="completeModal = false">Отмена</button>
        <button class="btn primary" :disabled="busy" @click="doComplete"><span v-if="busy" class="spinner"></span><span v-else>Завершить</span></button>
      </div>
    </Modal>

    <Modal v-model="amountModal" eyebrow="Сумма" :title="amountTitle">
      <div class="field">
        <label>{{ amountMode === 'add' ? 'Сколько добавить, ₸' : 'Новая сумма, ₸' }}</label>
        <input v-model="amountValue" type="number" min="0" class="input" autofocus
          :placeholder="amountMode === 'set' && amountField !== 'monthly_amount' ? 'пусто — не указана' : ''" />
        <span v-if="amountMode === 'add'" class="muted small">
          Сейчас {{ money(p[amountField]) }} → станет {{ money(Number(p[amountField] || 0) + Number(amountValue || 0)) }}
        </span>
      </div>
      <transition name="pop"><div v-if="modalError" class="badge red" style="margin-top: 8px">{{ modalError }}</div></transition>
      <div class="row between mt-16">
        <button class="btn ghost" @click="amountModal = false">Отмена</button>
        <button class="btn primary" :disabled="busy" @click="doAmount"><span v-if="busy" class="spinner"></span><span v-else>Сохранить</span></button>
      </div>
    </Modal>

    <Modal v-model="clientModal" eyebrow="Клиент" title="Данные клиента">
      <div class="grid-2">
        <div class="field"><label>Клиент</label><input v-model="client.client_name" class="input" placeholder="Имя или компания" /></div>
        <div class="field"><label>Номер клиента</label><input v-model="client.client_phone" class="input" type="tel" placeholder="+7 700 000 00 00" /></div>
      </div>
      <div class="row between mt-16">
        <button class="btn ghost" @click="clientModal = false">Отмена</button>
        <button class="btn primary" :disabled="busy" @click="saveClient"><span v-if="busy" class="spinner"></span><span v-else>Сохранить</span></button>
      </div>
    </Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api, { money, formatDate } from '../../api'
import StatCard from '../../components/StatCard.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import Icon from '../../components/Icon.vue'
import Modal from '../../components/Modal.vue'
import DeadlineBadge from '../../components/DeadlineBadge.vue'
import ReviewBadge from '../../components/ReviewBadge.vue'
import ReviewThread from '../../components/ReviewThread.vue'

const emit = defineEmits(['changed'])
const route = useRoute()
const p = ref(null)
const busy = ref(false)
const modalError = ref('')

// оплаты «за проект» (без ежемесячных; старые этапы тоже сюда)
const projectPayments = computed(() => (p.value?.payments || []).filter(x => x.kind !== 'monthly'))
const paid = computed(() => projectPayments.value.reduce((acc, x) => acc + Number(x.amount), 0))
const left = computed(() => Number(p.value?.price || 0) - paid.value)

async function load() {
  const { data } = await api.get(`/projects/${route.params.id}/`)
  p.value = data
}

function onReviewUpdate(fresh) { p.value = fresh; emit('changed') }

async function patch(body) {
  const { data } = await api.patch(`/projects/${p.value.id}/`, body)
  p.value = data
  emit('changed')
}

// ----- приём оплаты -----
const payModal = ref(false)
const payAmount = ref('')
function openPay() {
  payAmount.value = p.value.price && left.value > 0 ? left.value : ''
  modalError.value = ''
  payModal.value = true
}
async function doPay() {
  busy.value = true; modalError.value = ''
  try {
    await api.post(`/projects/${p.value.id}/add_payment/`, { kind: 'payment', amount: payAmount.value })
    payModal.value = false
    await load(); emit('changed')
  } catch (e) {
    modalError.value = e.response?.data?.detail || 'Не удалось провести оплату'
  } finally { busy.value = false }
}

// ----- завершение -----
const completeModal = ref(false)
function openComplete() { completeModal.value = true }
async function doComplete() {
  busy.value = true
  try {
    await api.post(`/projects/${p.value.id}/complete/`)
    completeModal.value = false
    await load(); emit('changed')
  } finally { busy.value = false }
}

// ----- суммы: изменить или добавить -----
const amountModal = ref(false)
const amountField = ref('price')
const amountMode = ref('set')
const amountValue = ref('')
const amountTitles = {
  price: ['Изменить сумму проекта', 'Добавить к сумме проекта'],
  worker_amount: ['Изменить сумму рабочему', 'Добавить к сумме рабочему'],
  monthly_amount: ['Изменить оплату в месяц', 'Добавить к оплате в месяц'],
}
const amountTitle = computed(() => amountTitles[amountField.value][amountMode.value === 'add' ? 1 : 0])
function openAmount(field, mode) {
  amountField.value = field
  amountMode.value = mode
  amountValue.value = mode === 'set' ? (p.value[field] ?? '') : ''
  modalError.value = ''
  amountModal.value = true
}
// старое имя — для кнопки ежемесячной оплаты
function openEditAmount(field) { openAmount(field, 'set') }
async function doAmount() {
  busy.value = true; modalError.value = ''
  try {
    const v = amountValue.value === '' ? null : Number(amountValue.value)
    const value = amountMode.value === 'add' ? Number(p.value[amountField.value] || 0) + (v || 0) : v
    await patch({ [amountField.value]: value })
    amountModal.value = false
  } catch (e) {
    modalError.value = e.response?.data?.detail || 'Не удалось сохранить'
  } finally { busy.value = false }
}

// ----- клиент -----
const clientModal = ref(false)
const client = ref({ client_name: '', client_phone: '' })
function openClient() {
  client.value = { client_name: p.value.client_name, client_phone: p.value.client_phone }
  clientModal.value = true
}
async function saveClient() {
  busy.value = true
  try {
    await patch({ client_name: client.value.client_name.trim(), client_phone: client.value.client_phone.trim() })
    clientModal.value = false
  } finally { busy.value = false }
}

async function payMonthly() {
  await api.post(`/projects/${p.value.id}/pay_monthly/`, {})
  await load(); emit('changed')
}

async function finish() {
  await api.post(`/projects/${p.value.id}/finish/`, {})
  await load(); emit('changed')
}
async function unfinish() {
  await api.post(`/projects/${p.value.id}/finish/`, { clear: true })
  await load(); emit('changed')
}

onMounted(load)
</script>

<style scoped>
.grid-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }
.two-col { display: grid; grid-template-columns: 1.6fr 1fr; gap: 16px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.dates { display: flex; gap: 12px; flex-wrap: wrap; }
.date-chip { display: flex; flex-direction: column; gap: 3px; padding: 12px 16px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); min-width: 120px; }
.amount { font-size: 20px; font-weight: 800; letter-spacing: -.01em; }
.stage-card { display: flex; flex-direction: column; gap: 6px; }
.bar { height: 8px; border-radius: 999px; background: var(--input-bg); overflow: hidden; margin-top: 6px; }
.bar-fill { height: 100%; border-radius: 999px; background: var(--c-emerald); transition: width .6s cubic-bezier(.16,1,.3,1); }
.srv { padding: 14px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); margin-bottom: 10px; }
@media (max-width: 1100px) { .grid-5 { grid-template-columns: repeat(2,1fr); } .two-col, .grid-3 { grid-template-columns: 1fr; } }
</style>
