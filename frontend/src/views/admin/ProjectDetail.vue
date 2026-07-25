<template>
  <div v-if="p">
    <button class="btn ghost sm" @click="$router.push('/projects')" style="margin-bottom: 16px"><Icon name="arrow-left" :size="16" /> К проектам</button>

    <div class="head card animate-in">
      <div class="row between wrap gap-16">
        <div>
          <div class="row gap-8 wrap">
            <StatusBadge :status="p.status" />
            <span v-if="p.has_stages" class="badge blue">Этапы</span>
            <span v-if="p.has_monthly" class="badge amber">Ежемесячная</span>
            <DeadlineBadge :status="p.deadline_status" />
          </div>
          <h1 class="h1" style="margin-top: 10px">{{ p.name }}</h1>
          <div class="muted mt-8 row gap-8 wrap"><Icon name="user" :size="15" /> Рабочий: <b style="color: var(--text)">{{ p.worker_name || p.worker_username }}</b>
            <span v-if="p.has_stages">· рабочему: бета <b style="color: var(--text)">{{ money(p.worker_beta_amount) }}</b> / сдача <b style="color: var(--text)">{{ money(p.worker_final_amount) }}</b></span>
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

    <!-- Этапы оплаты -->
    <div v-if="p.has_stages" class="mt-24">
      <h2 class="h2" style="margin-bottom: 12px">Этапы оплаты</h2>
      <div class="grid-3">
        <div class="card stage-card animate-in d1">
          <div class="row between mb-8"><b>Старт</b><StatusBadge :status="paidStages.has('start') ? 'done' : 'active'" /></div>
          <div class="row between mb-12" style="align-items: center">
            <span class="mono" style="font-size: 18px; font-weight: 700">{{ money(p.start_amount) }}</span>
            <button v-if="!paidStages.has('start') && p.status === 'active'" class="btn ghost icon-only sm" @click="openEditAmount('start_amount', p.start_amount)" style="padding: 4px; height: auto"><Icon name="edit" :size="14" /></button>
          </div>
          <button v-if="!paidStages.has('start') && p.status === 'active'" class="btn sm" @click="openPay('start', p.start_amount)">Оплатить старт</button>
          <div v-else class="muted small"><Icon name="check" :size="14" /> Оплачено</div>
        </div>
        <div class="card stage-card animate-in d2">
          <div class="row between mb-8"><b>Бета-версия</b><StatusBadge :status="paidStages.has('beta') ? 'done' : 'active'" /></div>
          <div class="row between mb-12" style="align-items: center">
            <span class="mono" style="font-size: 18px; font-weight: 700">{{ money(p.beta_amount) }}</span>
            <button v-if="!paidStages.has('beta') && p.status === 'active'" class="btn ghost icon-only sm" @click="openEditAmount('beta_amount', p.beta_amount)" style="padding: 4px; height: auto"><Icon name="edit" :size="14" /></button>
          </div>
          <button v-if="!paidStages.has('beta') && p.status === 'active'" class="btn sm" @click="openPay('beta', p.beta_amount)">Оплатить бету</button>
          <div v-else class="muted small"><Icon name="check" :size="14" /> Оплачено</div>
        </div>
        <div class="card stage-card animate-in d3">
          <div class="row between mb-8"><b>Сдача (Финал)</b><StatusBadge :status="paidStages.has('final') ? 'done' : 'active'" /></div>
          <div class="row between mb-12" style="align-items: center">
            <span class="mono" style="font-size: 18px; font-weight: 700">{{ money(p.final_amount) }}</span>
            <button v-if="!paidStages.has('final') && p.status === 'active'" class="btn ghost icon-only sm" @click="openEditAmount('final_amount', p.final_amount)" style="padding: 4px; height: auto"><Icon name="edit" :size="14" /></button>
          </div>
          <button v-if="!paidStages.has('final') && p.status === 'active'" class="btn sm" @click="openPay('final', p.final_amount)">Оплатить сдачу</button>
          <div v-else class="muted small"><Icon name="check" :size="14" /> Оплачено</div>
        </div>
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

    <Modal v-model="payModal" eyebrow="Платёж" :title="payTitle">
      <div v-if="!isComplete" class="field"><label>Сумма, ₸</label><input v-model="payAmount" type="number" class="input" autofocus /></div>
      <div v-else class="muted">Проект будет переведён в статус "Завершён".</div>
      <div class="row between mt-16">
        <button class="btn ghost" @click="payModal = false">Отмена</button>
        <button class="btn primary" :disabled="busy" @click="doPay"><span v-if="busy" class="spinner"></span><span v-else>Провести</span></button>
      </div>
    </Modal>

    <Modal v-model="editAmountModal" eyebrow="Редактировать" title="Изменить сумму">
      <div class="field"><label>Новая сумма, ₸</label><input v-model="editAmountValue" type="number" class="input" autofocus /></div>
      <div class="row between mt-16">
        <button class="btn ghost" @click="editAmountModal = false">Отмена</button>
        <button class="btn primary" :disabled="busy" @click="doEditAmount"><span v-if="busy" class="spinner"></span><span v-else>Сохранить</span></button>
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

const emit = defineEmits(['changed'])
const route = useRoute()
const p = ref(null)
const payModal = ref(false)
const payKind = ref('final')
const payAmount = ref('')
const busy = ref(false)
const isComplete = ref(false)

const editAmountModal = ref(false)
const editAmountField = ref('')
const editAmountValue = ref('')

const paidStages = computed(() => {
  if (!p.value) return new Set()
  return new Set(p.value.payments.map(pay => pay.kind))
})

const payTitle = computed(() => {
  if (isComplete.value) return 'Завершить проект?'
  const names = { start: 'Оплата: Старт', beta: 'Оплата: Бета', final: 'Оплата: Сдача' }
  return names[payKind.value] || 'Новый платёж'
})

async function load() {
  const { data } = await api.get(`/projects/${route.params.id}/`)
  p.value = data
}

function openPay(kind, amount) { payKind.value = kind; payAmount.value = amount; isComplete.value = false; payModal.value = true }
function openComplete() { isComplete.value = true; payModal.value = true }

function openEditAmount(field, value) {
  editAmountField.value = field
  editAmountValue.value = value
  editAmountModal.value = true
}

async function doPay() {
  busy.value = true
  try {
    if (isComplete.value) {
      await api.post(`/projects/${p.value.id}/complete/`)
    } else {
      await api.post(`/projects/${p.value.id}/add_payment/`, { kind: payKind.value, amount: payAmount.value })
    }
    payModal.value = false
    await load(); emit('changed')
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

async function doEditAmount() {
  busy.value = true
  try {
    await api.patch(`/projects/${p.value.id}/`, {
      [editAmountField.value]: editAmountValue.value
    })
    editAmountModal.value = false
    await load()
    emit('changed')
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.grid-5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; }
.two-col { display: grid; grid-template-columns: 1.6fr 1fr; gap: 16px; }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.dates { display: flex; gap: 12px; flex-wrap: wrap; }
.date-chip { display: flex; flex-direction: column; gap: 3px; padding: 12px 16px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); min-width: 120px; }
.srv { padding: 14px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); margin-bottom: 10px; }
@media (max-width: 1100px) { .grid-5 { grid-template-columns: repeat(2,1fr); } .two-col { grid-template-columns: 1fr; } }
</style>
