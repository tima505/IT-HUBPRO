<template>
  <div v-if="p" class="pd">
    <div class="row between wrap gap-8">
      <button class="btn ghost sm" @click="$router.push('/projects')"><Icon name="arrow-left" :size="16" /> К проектам</button>
      <button class="btn sm" @click="$router.push(`/projects/${p.id}/edit`)"><Icon name="edit" :size="15" /> Редактировать</button>
    </div>

    <!-- Шапка -->
    <div class="card head animate-in">
      <div class="head-main">
        <div class="row gap-8 wrap">
          <StatusBadge :status="p.status" />
          <span v-if="p.has_monthly" class="badge amber">Ежемесячно</span>
          <DeadlineBadge :status="p.deadline_status" />
        </div>
        <h1 class="h1">{{ p.name }}</h1>
        <p v-if="p.description" class="muted desc">{{ p.description }}</p>
        <div class="meta">
          <span v-if="p.client_name" class="meta-item"><Icon name="briefcase" :size="15" /> {{ p.client_name }}</span>
          <a v-if="p.client_phone" class="meta-item link" :href="`tel:${p.client_phone.replace(/[^\d+]/g, '')}`"><Icon name="phone" :size="15" /> {{ p.client_phone }}</a>
          <span class="meta-item"><Icon name="user" :size="15" /> {{ p.worker_name || p.worker_username }}</span>
        </div>
      </div>
      <div class="head-actions">
        <button v-if="!p.finished_date" class="btn green" @click="finish"><Icon name="check" :size="16" /> Отметить сдачу</button>
        <button v-else class="btn ghost" @click="unfinish"><Icon name="close" :size="15" /> Снять отметку сдачи</button>
        <button v-if="p.status === 'active'" class="btn" @click="complete"><Icon name="flag" :size="16" /> Завершить</button>
      </div>
    </div>

    <div class="pd-grid">
      <!-- Оплата клиента -->
      <section class="card pay-card animate-in d1">
        <div class="row between wrap gap-8">
          <div>
            <div class="eyebrow">Клиент</div>
            <h2 class="h2">Оплата проекта</h2>
          </div>
          <button v-if="Number(p.debt) > 0" class="btn primary" @click="openPayment"><Icon name="plus" :size="17" /> Принять оплату</button>
          <span v-else-if="Number(p.price) > 0" class="badge green"><Icon name="check-circle" :size="13" /> Оплачено полностью</span>
        </div>

        <div class="nums">
          <div class="num"><span class="muted small">Цена</span><b class="mono">{{ money(p.price) }}</b></div>
          <div class="num"><span class="muted small">Оплачено</span><b class="mono ok">{{ money(p.paid) }}</b></div>
          <div class="num debt" :class="{ zero: Number(p.debt) === 0 }"><span class="small">Осталось оплатить</span><b class="mono">{{ money(p.debt) }}</b></div>
        </div>
        <div v-if="Number(p.price) > 0" class="progress-wrap">
          <div class="progress big" :class="{ ok: p.paid_percent === 100 }"><span :style="{ width: (p.paid_percent || 0) + '%' }"></span></div>
          <span class="mono small muted">{{ p.paid_percent || 0 }}%</span>
        </div>

        <div class="hist-title">История оплат <span class="muted">· {{ priceHistory.length }}</span></div>
        <div v-if="!priceHistory.length" class="empty small">
          <div class="empty-ico"><Icon name="wallet" :size="20" /></div>
          Клиент ещё ничего не оплатил
        </div>
        <transition-group name="list" tag="ol" class="timeline">
          <li v-for="pay in priceHistory" :key="pay.id" class="tl">
            <span class="tl-dot"></span>
            <div class="tl-body">
              <div class="row between gap-8">
                <b class="mono tl-amount">+{{ money(pay.amount) }}</b>
                <span class="muted small">{{ formatDate(pay.date) }}</span>
              </div>
              <div class="row between gap-8 wrap">
                <span class="small">
                  <span v-if="pay.note">{{ pay.note }} · </span>
                  <span class="muted">остаток после:</span> <b class="mono" :class="{ okc: pay.after === 0 }">{{ money(pay.after) }}</b>
                </span>
                <button class="btn ghost sm icon-btn del" title="Удалить ошибочную оплату" @click="deletePayment(pay)"><Icon name="trash" :size="14" /></button>
              </div>
              <div class="split muted">
                {{ fundNames.f1 }} {{ money(pay.fund20_amount) }} · {{ fundNames.f2 }} {{ money(pay.fund5_amount) }} · компании {{ money(pay.company_amount) }}
              </div>
            </div>
          </li>
        </transition-group>
      </section>

      <div class="side">
        <!-- Рабочий -->
        <section class="card animate-in d2">
          <div class="row between wrap gap-8">
            <div>
              <div class="eyebrow">Рабочий</div>
              <h2 class="h2">{{ p.worker_name || p.worker_username }}</h2>
            </div>
            <button v-if="Number(p.worker_debt) > 0" class="btn sm green" @click="openPayout"><Icon name="wallet" :size="15" /> Выплатить</button>
          </div>
          <div class="nums three">
            <div class="num"><span class="muted small">Должны</span><b class="mono">{{ money(p.worker_amount) }}</b></div>
            <div class="num"><span class="muted small">Выплачено</span><b class="mono ok">{{ money(p.worker_paid) }}</b></div>
            <div class="num"><span class="muted small">Осталось</span><b class="mono" :class="Number(p.worker_debt) > 0 ? 'warn' : 'ok'">{{ money(p.worker_debt) }}</b></div>
          </div>
          <div v-if="Number(p.worker_amount) > 0" class="progress"><span :style="{ width: Math.min(100, p.worker_paid / p.worker_amount * 100) + '%' }"></span></div>
          <div v-if="p.payouts.length" class="mini-list">
            <div v-for="po in p.payouts" :key="po.id" class="mini">
              <div class="grow">
                <b class="mono">{{ money(po.amount) }}</b>
                <div class="muted small">{{ formatDate(po.date) }} · из «{{ bucketName(po.paid_from) }}»<span v-if="po.note"> · {{ po.note }}</span></div>
              </div>
              <button class="btn ghost sm icon-btn del" title="Удалить ошибочную выплату" @click="deletePayout(po)"><Icon name="trash" :size="14" /></button>
            </div>
          </div>
          <div v-else-if="Number(p.worker_amount) > 0" class="muted small">Выплат пока не было</div>
        </section>

        <!-- Ежемесячно -->
        <section v-if="p.has_monthly" class="card animate-in d3">
          <div class="eyebrow">Обслуживание</div>
          <div class="row between wrap gap-8 mt-8">
            <div>
              <b class="mono month-amt">{{ money(p.monthly_amount) }}</b><span class="muted"> / мес</span>
              <div class="muted small">Следующая оплата: <b>{{ formatDate(p.monthly_next_due) }}</b></div>
            </div>
            <button v-if="p.status === 'active'" class="btn sm" @click="payMonthly"><Icon name="check" :size="14" /> Оплачено</button>
          </div>
          <div v-if="monthlyHistory.length" class="mini-list">
            <div v-for="pay in monthlyHistory" :key="pay.id" class="mini">
              <span class="grow muted small">{{ formatDate(pay.date) }}</span>
              <b class="mono">{{ money(pay.amount) }}</b>
            </div>
          </div>
        </section>

        <!-- Сроки -->
        <section class="card animate-in d3">
          <div class="eyebrow" style="margin-bottom: 10px">Сроки</div>
          <div class="dates">
            <div><span class="muted small">Начало</span><b>{{ formatDate(p.start_date) }}</b></div>
            <div><span class="muted small">Бета</span><b>{{ formatDate(p.beta_date) }}</b></div>
            <div><span class="muted small">Дедлайн</span><b>{{ formatDate(p.deadline_date) }}</b></div>
            <div><span class="muted small">Сдал рабочий</span><b>{{ p.finished_date ? formatDate(p.finished_date) : '—' }}</b></div>
          </div>
        </section>

        <!-- Серверы -->
        <section v-if="p.servers.length" class="card animate-in d4">
          <div class="eyebrow" style="margin-bottom: 10px">Серверы</div>
          <div v-for="s in p.servers" :key="s.id" class="mini">
            <div class="grow">
              <b>{{ s.label }}</b>
              <div class="muted small"><Icon name="key" :size="13" /> {{ s.login || '—' }} · до {{ formatDate(s.expiry_date) }}</div>
            </div>
            <span class="badge" :class="s.days_left <= 1 ? 'red' : (s.days_left <= 7 ? 'amber' : 'green')">{{ s.days_left < 0 ? 'истёк' : `${s.days_left} дн.` }}</span>
          </div>
        </section>
      </div>
    </div>

    <!-- Принять оплату -->
    <Modal v-model="payModal" eyebrow="Оплата клиента" :title="p.name">
      <form class="mform" @submit.prevent="submitPayment">
        <div class="debt-line">Осталось оплатить: <b class="mono">{{ money(p.debt) }}</b></div>
        <div class="field">
          <label>Сумма оплаты</label>
          <MoneyInput ref="payInput" v-model="payForm.amount" size="lg" placeholder="100 000" />
          <div class="chips">
            <button type="button" class="chip" @click="payForm.amount = Number(p.debt)">Весь остаток</button>
            <button v-for="v in quickAmounts" :key="v" type="button" class="chip" @click="payForm.amount = v">{{ money(v) }}</button>
          </div>
        </div>
        <div class="grid-2">
          <div class="field"><label>Дата</label><input v-model="payForm.date" type="date" class="input" :max="today" /></div>
          <div class="field"><label>Комментарий</label><input v-model="payForm.note" class="input" placeholder="Kaspi, наличные…" maxlength="255" /></div>
        </div>
        <div v-if="payForm.amount" class="after" :class="{ bad: payForm.amount > Number(p.debt) }">
          <template v-if="payForm.amount > Number(p.debt)">Больше остатка долга на {{ money(payForm.amount - p.debt) }}</template>
          <template v-else>После оплаты останется: <b class="mono">{{ money(p.debt - payForm.amount) }}</b></template>
        </div>
        <div v-if="formError" class="badge red">{{ formError }}</div>
        <div class="row between">
          <button type="button" class="btn ghost" @click="payModal = false">Отмена</button>
          <button class="btn primary" :disabled="busy || !payForm.amount || payForm.amount > Number(p.debt)">
            <span v-if="busy" class="spinner"></span><template v-else><Icon name="check" :size="16" /> Принять</template>
          </button>
        </div>
      </form>
    </Modal>

    <!-- Выплатить рабочему -->
    <Modal v-model="payoutModal" eyebrow="Выплата рабочему" :title="p.worker_name || p.worker_username">
      <form class="mform" @submit.prevent="submitPayout">
        <div class="debt-line">Осталось выплатить: <b class="mono">{{ money(p.worker_debt) }}</b></div>
        <div class="field">
          <label>Сумма выплаты</label>
          <MoneyInput v-model="payoutForm.amount" size="lg" placeholder="50 000" />
          <div class="chips"><button type="button" class="chip" @click="payoutForm.amount = Number(p.worker_debt)">Весь остаток</button></div>
        </div>
        <div class="field">
          <label>Из каких денег</label>
          <div class="buckets">
            <button v-for="b in buckets" :key="b.key" type="button" class="bucket" :class="{ on: payoutForm.paid_from === b.key }" @click="payoutForm.paid_from = b.key">
              <span>{{ b.name }}</span><b class="mono">{{ money(b.balance) }}</b>
            </button>
          </div>
        </div>
        <div class="grid-2">
          <div class="field"><label>Дата</label><input v-model="payoutForm.date" type="date" class="input" :max="today" /></div>
          <div class="field"><label>Комментарий</label><input v-model="payoutForm.note" class="input" placeholder="Аванс, за бету…" maxlength="255" /></div>
        </div>
        <div v-if="formError" class="badge red">{{ formError }}</div>
        <div class="row between">
          <button type="button" class="btn ghost" @click="payoutModal = false">Отмена</button>
          <button class="btn primary" :disabled="busy || !payoutForm.amount">
            <span v-if="busy" class="spinner"></span><template v-else><Icon name="check" :size="16" /> Выплатить</template>
          </button>
        </div>
      </form>
    </Modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import api, { money, formatDate, errorMessage } from '../../api'
import StatusBadge from '../../components/StatusBadge.vue'
import DeadlineBadge from '../../components/DeadlineBadge.vue'
import Icon from '../../components/Icon.vue'
import Modal from '../../components/Modal.vue'
import MoneyInput from '../../components/MoneyInput.vue'

const emit = defineEmits(['changed'])
const route = useRoute()
const p = ref(null)
const settings = ref({ fund1_name: 'Фонд 20%', fund2_name: 'Фонд 5%' })
const finance = ref(null)
const busy = ref(false)
const formError = ref('')
const now = new Date()
const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

const fundNames = computed(() => ({ f1: settings.value.fund1_name, f2: settings.value.fund2_name }))
function bucketName(key) {
  return { company: 'Деньги компании', fund20: settings.value.fund1_name, fund5: settings.value.fund2_name }[key] || key
}
const buckets = computed(() => [
  { key: 'company', name: 'Деньги компании', balance: finance.value?.company?.balance ?? 0 },
  { key: 'fund20', name: settings.value.fund1_name, balance: finance.value?.fund20?.balance ?? 0 },
  { key: 'fund5', name: settings.value.fund2_name, balance: finance.value?.fund5?.balance ?? 0 },
])

// оплаты в счёт цены: от старых к новым считаем остаток после каждой, показываем новые сверху
const priceHistory = computed(() => {
  const list = [...p.value.payments].filter(x => x.kind !== 'monthly')
    .sort((a, b) => a.date.localeCompare(b.date) || a.id - b.id)
  let paid = 0
  const rows = list.map(x => {
    paid += Number(x.amount)
    return { ...x, after: Math.max(Number(p.value.price) - paid, 0) }
  })
  return rows.reverse()
})
const monthlyHistory = computed(() => p.value.payments.filter(x => x.kind === 'monthly'))
const quickAmounts = computed(() => [50000, 100000, 200000].filter(v => v < Number(p.value.debt)))

async function load() {
  const [pr, s] = await Promise.all([api.get(`/projects/${route.params.id}/`), api.get('/settings/')])
  p.value = pr.data
  settings.value = s.data
}
function changed(data) {
  if (data) p.value = data
  emit('changed')
}

// --- оплата клиента
const payModal = ref(false)
const payInput = ref(null)
const payForm = reactive({ amount: null, date: today, note: '' })
async function openPayment() {
  Object.assign(payForm, { amount: null, date: today, note: '' })
  formError.value = ''
  payModal.value = true
  await nextTick()
  payInput.value?.focus()
}
async function submitPayment() {
  busy.value = true; formError.value = ''
  try {
    const { data } = await api.post(`/projects/${p.value.id}/add_payment/`, payForm, { silentError: true })
    payModal.value = false
    changed(data)
  } catch (e) { formError.value = errorMessage(e) } finally { busy.value = false }
}
async function deletePayment(pay) {
  if (!confirm(`Удалить оплату ${money(pay.amount)} от ${formatDate(pay.date)}? Долг клиента увеличится.`)) return
  const { data } = await api.delete(`/projects/${p.value.id}/payments/${pay.id}/`)
  changed(data)
}

// --- выплата рабочему
const payoutModal = ref(false)
const payoutForm = reactive({ amount: null, date: today, note: '', paid_from: 'company' })
async function openPayout() {
  Object.assign(payoutForm, { amount: null, date: today, note: '', paid_from: 'company' })
  formError.value = ''
  payoutModal.value = true
  finance.value = (await api.get('/finance/')).data
}
async function submitPayout() {
  busy.value = true; formError.value = ''
  try {
    const { data } = await api.post(`/projects/${p.value.id}/pay_worker/`, payoutForm, { silentError: true })
    payoutModal.value = false
    changed(data)
  } catch (e) { formError.value = errorMessage(e) } finally { busy.value = false }
}
async function deletePayout(po) {
  if (!confirm(`Удалить выплату ${money(po.amount)} от ${formatDate(po.date)}? Деньги вернутся в «${bucketName(po.paid_from)}».`)) return
  const { data } = await api.delete(`/projects/${p.value.id}/payouts/${po.id}/`)
  changed(data)
}

// --- статусы
async function payMonthly() { changed((await api.post(`/projects/${p.value.id}/pay_monthly/`, {})).data) }
async function finish() { changed((await api.post(`/projects/${p.value.id}/finish/`, {})).data) }
async function unfinish() { changed((await api.post(`/projects/${p.value.id}/finish/`, { clear: true })).data) }
async function complete() {
  const debt = Number(p.value.debt)
  const msg = debt > 0
    ? `У клиента остался долг ${money(debt)}. Всё равно завершить проект? Долг останется в разделе «Долги».`
    : 'Завершить проект?'
  if (!confirm(msg)) return
  changed((await api.post(`/projects/${p.value.id}/complete/`)).data)
}

onMounted(load)
</script>

<style scoped>
.pd { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; justify-content: space-between; gap: 20px; flex-wrap: wrap; position: relative; overflow: hidden; }
.head::after { content: ''; position: absolute; inset: 0 0 auto; height: 3px; background: var(--grad-tech); }
.head-main { display: flex; flex-direction: column; gap: 10px; min-width: 0; flex: 1; }
.desc { margin: 0; max-width: 720px; line-height: 1.5; }
.meta { display: flex; gap: 8px 18px; flex-wrap: wrap; color: var(--muted); font-size: 14px; }
.meta-item { display: inline-flex; align-items: center; gap: 6px; }
.meta-item.link { color: var(--brand); }
[data-theme='dark'] .meta-item.link { color: var(--info-fg); }
.head-actions { display: flex; gap: 8px; align-items: flex-start; flex-wrap: wrap; }

.pd-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 16px; align-items: start; }
.side { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.pay-card { display: flex; flex-direction: column; gap: 16px; }

.nums { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.nums.three { margin: 14px 0 10px; }
.num { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; border-radius: 14px; background: var(--card-2); border: 1px solid var(--stroke); min-width: 0; }
.num b { font-size: 19px; letter-spacing: -.01em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nums.three .num b { font-size: 15px; }
.num.debt { background: var(--bad-bg); border-color: transparent; color: var(--bad-fg); }
.num.debt b { font-size: 22px; }
.num.debt.zero { background: var(--ok-bg); color: var(--ok-fg); }
.ok { color: var(--ok-fg); } .warn { color: var(--warn-fg); } .okc { color: var(--ok-fg); }
.progress-wrap { display: flex; align-items: center; gap: 10px; }
.progress-wrap .progress { flex: 1; }
.progress.big { height: 10px; }

.hist-title { font-weight: 700; padding-top: 6px; border-top: 1px solid var(--stroke); padding-top: 16px; }
.timeline { list-style: none; margin: 0; padding: 0 0 0 6px; display: flex; flex-direction: column; position: relative; }
.tl { position: relative; padding: 0 0 16px 22px; }
.tl::before { content: ''; position: absolute; left: 4px; top: 14px; bottom: -2px; width: 2px; background: var(--stroke); }
.tl:last-child::before { display: none; }
.tl-dot { position: absolute; left: 0; top: 6px; width: 10px; height: 10px; border-radius: 50%; background: var(--c-emerald); box-shadow: 0 0 0 3px var(--ok-bg); }
.tl-body { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: 12px; background: var(--card-2); border: 1px solid var(--stroke); }
.tl-amount { font-size: 16px; color: var(--ok-fg); }
.split { font-size: 12px; }
.del { color: var(--muted-2); }
.del:hover { color: var(--bad-fg); }

.mini-list { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
.mini { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 12px; background: var(--card-2); border: 1px solid var(--stroke); }
.mini + .mini { margin-top: 0; }
.month-amt { font-size: 20px; }
.dates { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.dates > div { display: flex; flex-direction: column; gap: 3px; padding: 10px 12px; border-radius: 12px; background: var(--card-2); border: 1px solid var(--stroke); }

.mform { display: flex; flex-direction: column; gap: 14px; }
.debt-line { padding: 10px 14px; border-radius: 12px; background: var(--info-bg); font-size: 14px; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { border: 1px solid var(--stroke); background: var(--card-2); color: var(--muted); font: 600 12px var(--font);
  padding: 5px 10px; border-radius: 99px; cursor: pointer; transition: all .2s; }
.chip:hover { color: var(--text); border-color: var(--brand); }
.after { font-size: 14px; color: var(--muted); }
.after.bad { color: var(--bad-fg); }
.buckets { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.bucket { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; text-align: left; border-radius: 12px; cursor: pointer;
  border: 1px solid var(--stroke); background: var(--card-2); color: var(--muted); font: 500 12.5px var(--font); }
.bucket b { color: var(--text); font-size: 14px; }
.bucket.on { border-color: var(--brand); background: var(--info-bg); }

@media (max-width: 1100px) { .pd-grid { grid-template-columns: 1fr; } }
@media (max-width: 640px) {
  .nums { grid-template-columns: 1fr 1fr; }
  .nums .num.debt { grid-column: 1 / -1; order: -1; }
  .nums.three { grid-template-columns: repeat(3, 1fr); }
  .head-actions { width: 100%; }
  .head-actions .btn { flex: 1; }
  .buckets { grid-template-columns: 1fr; }
}
</style>
