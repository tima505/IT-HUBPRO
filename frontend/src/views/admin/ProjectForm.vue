<template>
  <div class="pf">
    <div class="pf-head">
      <button class="btn ghost sm" @click="back"><Icon name="arrow-left" :size="16" /> {{ isEdit ? 'К проекту' : 'К проектам' }}</button>
      <div v-if="!workers.length && loaded" class="badge amber"><Icon name="alert" :size="13" /> Сначала создайте рабочего во вкладке «Рабочие»</div>
    </div>

    <form class="pf-grid" @submit.prevent="save" novalidate>
      <!-- 01 · Проект и клиент -->
      <section class="col card">
        <header class="col-head">
          <span class="step">01</span>
          <div><h2 class="h2">Проект и клиент</h2><div class="muted small">Что делаем и для кого</div></div>
        </header>

        <div class="field">
          <label for="pf-name">Название проекта *</label>
          <input id="pf-name" v-model="form.name" class="input" placeholder="Напр. Интернет-магазин" maxlength="200" />
        </div>
        <div class="field">
          <label for="pf-desc">Описание</label>
          <textarea id="pf-desc" v-model="form.description" class="input" rows="3" placeholder="Что входит в проект, ссылки на ТЗ…"></textarea>
        </div>

        <div class="field">
          <label>Исполнитель *</label>
          <div class="people">
            <button v-for="w in workers" :key="w.id" type="button" class="person" :class="{ on: form.worker === w.id }" @click="form.worker = w.id">
              <span class="avatar sm">{{ initials(w.full_name || w.username) }}</span>
              <span class="grow ellipsis">{{ w.full_name || w.username }}</span>
              <span class="tick"><Icon name="check" :size="14" :stroke-width="3" /></span>
            </button>
          </div>
        </div>

        <div class="divider"><span>Клиент</span></div>
        <div class="field">
          <label for="pf-client">Имя / компания</label>
          <input id="pf-client" v-model="form.client_name" class="input" list="pf-clients" placeholder="ТОО «Компания» или ФИО" maxlength="200" @change="fillPhone" />
          <datalist id="pf-clients">
            <option v-for="c in knownClients" :key="c.name + c.phone" :value="c.name">{{ c.phone }}</option>
          </datalist>
        </div>
        <div class="field">
          <label for="pf-phone">Телефон</label>
          <input id="pf-phone" v-model="form.client_phone" class="input" type="tel" inputmode="tel" placeholder="+7 7__ ___ __ __" maxlength="30" />
        </div>
      </section>

      <!-- 02 · Деньги -->
      <section class="col card money-col">
        <header class="col-head">
          <span class="step">02</span>
          <div><h2 class="h2">Деньги</h2><div class="muted small">Одна цена — клиент платит частями</div></div>
        </header>

        <div class="field">
          <label for="pf-price">Цена проекта {{ form.has_monthly ? '' : '*' }}</label>
          <MoneyInput id="pf-price" v-model="form.price" size="lg" placeholder="500 000" />
          <div class="chips">
            <button v-for="v in [300000, 500000, 1000000]" :key="v" type="button" class="chip" @click="form.price = v">{{ short(v) }}</button>
          </div>
        </div>

        <div class="field">
          <label for="pf-worker">Должны рабочему</label>
          <MoneyInput id="pf-worker" v-model="form.worker_amount" placeholder="100 000" />
          <div class="muted small">Выплаты рабочему записываются в карточке проекта по мере оплаты.</div>
        </div>

        <div v-if="!isEdit" class="field">
          <label for="pf-pre">Предоплата клиента <span class="muted">(если уже внёс)</span></label>
          <div class="row gap-8">
            <MoneyInput id="pf-pre" v-model="form.prepayment" class="grow" placeholder="0" />
            <input v-if="form.prepayment" v-model="form.prepayment_date" type="date" class="input pre-date" :max="today" />
          </div>
          <div v-if="form.price" class="chips">
            <button v-for="pct in [30, 50, 100]" :key="pct" type="button" class="chip" @click="form.prepayment = Math.round(form.price * pct / 100)">{{ pct }}%</button>
          </div>
        </div>

        <div class="opt" :class="{ on: ownRates }">
          <label class="switch-row">
            <span class="grow"><b>Свои ставки фондов</b><span class="muted small">По умолчанию {{ settings.fund1_rate }}% / {{ settings.fund2_rate }}% из настроек</span></span>
            <input type="checkbox" v-model="ownRates" class="switch" />
          </label>
          <div v-if="ownRates" class="opt-body grid-2">
            <div class="field"><label>{{ settings.fund1_name }}, %</label><input v-model="form.fund1_rate" type="number" min="0" max="100" step="0.5" class="input" /></div>
            <div class="field"><label>{{ settings.fund2_name }}, %</label><input v-model="form.fund2_rate" type="number" min="0" max="100" step="0.5" class="input" /></div>
          </div>
        </div>

        <!-- Живой расчёт -->
        <div class="calc">
          <div class="calc-title">Распределение цены</div>
          <div class="bar" v-if="calc.price > 0">
            <span class="seg f1" :style="{ flex: calc.f1 }" :title="settings.fund1_name"></span>
            <span class="seg f2" :style="{ flex: calc.f2 }" :title="settings.fund2_name"></span>
            <span class="seg wk" :style="{ flex: calc.worker }" title="Рабочему"></span>
            <span class="seg co" :style="{ flex: Math.max(calc.company, 0) }" title="Компании"></span>
          </div>
          <div class="calc-rows">
            <div><i class="dot f1"></i>{{ settings.fund1_name }} <span class="muted">· {{ rates.r1 }}%</span><b class="mono">{{ money(calc.f1) }}</b></div>
            <div><i class="dot f2"></i>{{ settings.fund2_name }} <span class="muted">· {{ rates.r2 }}%</span><b class="mono">{{ money(calc.f2) }}</b></div>
            <div><i class="dot wk"></i>Рабочему<b class="mono">{{ money(calc.worker) }}</b></div>
            <div class="total" :class="{ bad: calc.company < 0 }"><i class="dot co"></i>Остаётся компании<b class="mono">{{ money(calc.company) }}</b></div>
          </div>
          <div v-if="calc.company < 0" class="badge red">Доля рабочего больше, чем остаётся после фондов</div>
        </div>
      </section>

      <!-- 03 · Сроки и опции -->
      <section class="col card">
        <header class="col-head">
          <span class="step">03</span>
          <div><h2 class="h2">Сроки и опции</h2><div class="muted small">Даты, обслуживание, сервер</div></div>
        </header>

        <div class="grid-2">
          <div class="field">
            <label for="pf-start">Начало *</label>
            <input id="pf-start" v-model="form.start_date" type="date" class="input" />
          </div>
          <div class="field">
            <label for="pf-dl">Дедлайн *</label>
            <input id="pf-dl" v-model="form.deadline_date" type="date" class="input" :min="form.start_date" />
          </div>
        </div>
        <div class="chips">
          <button v-for="d in deadlinePresets" :key="d.label" type="button" class="chip" @click="setDeadline(d)">{{ d.label }}</button>
        </div>
        <div class="field">
          <label for="pf-beta">Показ бета-версии</label>
          <input id="pf-beta" v-model="form.beta_date" type="date" class="input" :min="form.start_date" :max="form.deadline_date" />
        </div>

        <div class="opt" :class="{ on: form.has_monthly }">
          <label class="switch-row">
            <span class="grow"><b>Ежемесячное обслуживание</b><span class="muted small">Клиент платит каждый месяц</span></span>
            <input type="checkbox" v-model="form.has_monthly" class="switch" />
          </label>
          <div v-if="form.has_monthly" class="opt-body">
            <div class="field">
              <label for="pf-monthly">Оплата в месяц *</label>
              <MoneyInput id="pf-monthly" v-model="form.monthly_amount" placeholder="50 000" />
            </div>
          </div>
        </div>

        <div v-if="!isEdit" class="opt" :class="{ on: form.has_server }">
          <label class="switch-row">
            <span class="grow"><b>Куплен сервер</b><span class="muted small">Добавится в «Серверы» с напоминаниями</span></span>
            <input type="checkbox" v-model="form.has_server" class="switch" />
          </label>
          <div v-if="form.has_server" class="opt-body">
            <div class="grid-2">
              <div class="field"><label>Логин</label><input v-model="form.server_login" class="input" placeholder="root" autocomplete="off" /></div>
              <div class="field"><label>Пароль</label><input v-model="form.server_password" class="input" placeholder="••••••" autocomplete="off" /></div>
            </div>
            <div class="field">
              <label>Срок</label>
              <div class="segmented full">
                <button type="button" :class="{ active: form.server_days === 30 }" @click="form.server_days = 30">Месяц</button>
                <button type="button" :class="{ active: form.server_days === 90 }" @click="form.server_days = 90">3 месяца</button>
                <button type="button" :class="{ active: form.server_days === 365 }" @click="form.server_days = 365">Год</button>
              </div>
            </div>
            <div class="grid-2">
              <div class="field"><label>Стоимость</label><MoneyInput v-model="form.server_amount" placeholder="45 000" /></div>
              <div class="field">
                <label>Оплачено из</label>
                <select v-model="form.server_paid_from" class="select input">
                  <option value="company">Деньги компании</option>
                  <option value="fund20">{{ settings.fund1_name }}</option>
                  <option value="fund5">{{ settings.fund2_name }}</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Итог + сохранение -->
      <div class="pf-bar">
        <div class="sum">
          <div><span class="muted small">Цена</span><b class="mono">{{ money(form.price || 0) }}</b></div>
          <div v-if="!isEdit" class="hide-m"><span class="muted small">Долг клиента после предоплаты</span><b class="mono">{{ money(Math.max((form.price || 0) - (form.prepayment || 0), 0)) }}</b></div>
          <div v-if="form.has_monthly" class="hide-m"><span class="muted small">В месяц</span><b class="mono">{{ money(form.monthly_amount || 0) }}</b></div>
        </div>
        <div v-if="error" class="badge red err">{{ error }}</div>
        <div class="row gap-8 actions">
          <button type="button" class="btn ghost hide-m" @click="back">Отмена</button>
          <button class="btn primary" :disabled="saving">
            <span v-if="saving" class="spinner"></span>
            <template v-else><Icon name="check" :size="17" /> {{ isEdit ? 'Сохранить' : 'Создать проект' }}</template>
          </button>
        </div>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api, { money, errorMessage } from '../../api'
import Icon from '../../components/Icon.vue'
import MoneyInput from '../../components/MoneyInput.vue'

const emit = defineEmits(['changed'])
const route = useRoute()
const router = useRouter()
const isEdit = computed(() => !!route.params.id)

const today = localIso(new Date())
function localIso(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const form = reactive({
  name: '', description: '', worker: null, client_name: '', client_phone: '',
  price: null, worker_amount: null, prepayment: null, prepayment_date: today,
  start_date: today, deadline_date: '', beta_date: '',
  has_monthly: false, monthly_amount: null, fund1_rate: null, fund2_rate: null,
  has_server: false, server_login: '', server_password: '', server_days: 30, server_amount: null, server_paid_from: 'company',
})
const workers = ref([])
const projects = ref([])
const settings = ref({ fund1_name: 'Фонд 20%', fund1_rate: 20, fund2_name: 'Фонд 5%', fund2_rate: 5 })
const loaded = ref(false)
const saving = ref(false)
const error = ref('')

const ownRates = ref(false)
const rates = computed(() => ({
  r1: ownRates.value && form.fund1_rate !== null && form.fund1_rate !== '' ? Number(form.fund1_rate) : Number(settings.value.fund1_rate),
  r2: ownRates.value && form.fund2_rate !== null && form.fund2_rate !== '' ? Number(form.fund2_rate) : Number(settings.value.fund2_rate),
}))
const calc = computed(() => {
  const price = Number(form.price) || 0
  const f1 = Math.round(price * rates.value.r1 / 100)
  const f2 = Math.round(price * rates.value.r2 / 100)
  const worker = Number(form.worker_amount) || 0
  return { price, f1, f2, worker, company: price - f1 - f2 - worker }
})

// клиенты из прошлых проектов — подсказки в поле «Клиент»
const knownClients = computed(() => {
  const seen = new Map()
  for (const p of projects.value) {
    if (p.client_name && !seen.has(p.client_name)) seen.set(p.client_name, { name: p.client_name, phone: p.client_phone })
  }
  return [...seen.values()]
})
function fillPhone() {
  const c = knownClients.value.find(c => c.name === form.client_name)
  if (c && !form.client_phone) form.client_phone = c.phone
}

const deadlinePresets = [
  { label: '+2 недели', days: 14 },
  { label: '+1 месяц', months: 1 },
  { label: '+2 месяца', months: 2 },
  { label: '+3 месяца', months: 3 },
]
function setDeadline(p) {
  const d = new Date((form.start_date || today) + 'T00:00:00')
  if (p.days) d.setDate(d.getDate() + p.days)
  if (p.months) d.setMonth(d.getMonth() + p.months)
  form.deadline_date = localIso(d)
}

function short(v) { return v >= 1000000 ? `${v / 1000000} млн` : `${v / 1000} тыс` }
function initials(n = '') { return n.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase() }

function validate() {
  if (!form.name.trim()) return 'Введите название проекта'
  if (!form.worker) return 'Выберите исполнителя'
  if (!form.price && !form.has_monthly) return 'Укажите цену проекта'
  if (!form.start_date || !form.deadline_date) return 'Укажите даты начала и дедлайна'
  if (form.has_monthly && !form.monthly_amount) return 'Укажите сумму ежемесячной оплаты'
  if (!isEdit.value && (form.prepayment || 0) > (form.price || 0)) return 'Предоплата больше цены проекта'
  if (ownRates.value && rates.value.r1 + rates.value.r2 > 100) return 'Ставки фондов в сумме не могут быть больше 100%'
  return ''
}

async function save() {
  error.value = validate()
  if (error.value) return
  saving.value = true
  const payload = {
    name: form.name.trim(), description: form.description, worker: form.worker,
    client_name: form.client_name.trim(), client_phone: form.client_phone.trim(),
    price: form.price || 0, worker_amount: form.worker_amount || 0,
    start_date: form.start_date, deadline_date: form.deadline_date, beta_date: form.beta_date || null,
    has_monthly: form.has_monthly, monthly_amount: form.has_monthly ? form.monthly_amount : null,
    // свои ставки проекта; выключено — берутся общие из настроек
    fund1_rate: ownRates.value && form.fund1_rate !== '' ? form.fund1_rate : null,
    fund2_rate: ownRates.value && form.fund2_rate !== '' ? form.fund2_rate : null,
  }
  try {
    let id = route.params.id
    if (isEdit.value) {
      await api.patch(`/projects/${id}/`, payload, { silentError: true })
    } else {
      Object.assign(payload, {
        prepayment: form.prepayment || null,
        prepayment_date: form.prepayment ? form.prepayment_date : null,
        has_server: form.has_server,
        ...(form.has_server && {
          server_login: form.server_login, server_password: form.server_password,
          server_days: form.server_days, server_amount: form.server_amount || 0,
          server_paid_from: form.server_paid_from,
        }),
      })
      id = (await api.post('/projects/', payload, { silentError: true })).data.id
    }
    emit('changed')
    router.push(`/projects/${id}`)
  } catch (e) {
    error.value = errorMessage(e, 'Проверьте поля формы')
  } finally { saving.value = false }
}

function back() { router.push(isEdit.value ? `/projects/${route.params.id}` : '/projects') }

onMounted(async () => {
  const [w, p, s] = await Promise.all([api.get('/users/', { params: { role: 'worker' } }), api.get('/projects/'), api.get('/settings/')])
  workers.value = w.data
  projects.value = p.data
  settings.value = s.data
  if (isEdit.value) {
    const pr = p.data.find(x => String(x.id) === String(route.params.id)) || (await api.get(`/projects/${route.params.id}/`)).data
    Object.assign(form, {
      name: pr.name, description: pr.description, worker: pr.worker,
      client_name: pr.client_name, client_phone: pr.client_phone,
      price: Number(pr.price) || null, worker_amount: Number(pr.worker_amount) || null,
      start_date: pr.start_date, deadline_date: pr.deadline_date, beta_date: pr.beta_date || '',
      has_monthly: pr.has_monthly, monthly_amount: pr.monthly_amount ? Number(pr.monthly_amount) : null,
      fund1_rate: pr.fund1_rate, fund2_rate: pr.fund2_rate,
    })
    ownRates.value = pr.fund1_rate !== null || pr.fund2_rate !== null
  } else if (workers.value.length === 1) {
    form.worker = workers.value[0].id
  }
  loaded.value = true
})
</script>

<style scoped>
.pf { display: flex; flex-direction: column; gap: 16px; padding-bottom: 90px; }
.pf-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.pf-grid { display: grid; grid-template-columns: 1fr 1.1fr 1fr; gap: 16px; align-items: start; }
.col { display: flex; flex-direction: column; gap: 14px; }
.col-head { display: flex; align-items: center; gap: 12px; padding-bottom: 14px; border-bottom: 1px solid var(--stroke); }
.step {
  font-family: var(--font-mono); font-weight: 600; font-size: 13px; width: 40px; height: 40px; border-radius: 12px;
  display: grid; place-items: center; flex-shrink: 0; color: #fff; background: var(--grad-brand); box-shadow: var(--brand-glow);
}

.people { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
.person {
  display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 12px; cursor: pointer; text-align: left;
  border: 1px solid var(--stroke); background: var(--card-2); color: var(--text); font: 600 13.5px var(--font); transition: all .2s;
}
.person:hover { border-color: var(--stroke-strong); }
.person.on { border-color: var(--brand); background: var(--info-bg); }
.tick { width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center; flex-shrink: 0;
  border: 1.5px solid var(--stroke-strong); color: transparent; transition: all .2s; }
.person.on .tick { background: var(--brand); border-color: var(--brand); color: #fff; }

.divider { display: flex; align-items: center; gap: 10px; margin-top: 4px; font-family: var(--font-mono); font-size: 11px;
  letter-spacing: .12em; text-transform: uppercase; color: var(--muted-2); }
.divider::after { content: ''; flex: 1; height: 1px; background: var(--stroke); }

.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { border: 1px solid var(--stroke); background: var(--card-2); color: var(--muted); font: 600 12px var(--font);
  padding: 5px 10px; border-radius: 99px; cursor: pointer; transition: all .2s; }
.chip:hover { color: var(--text); border-color: var(--brand); }
.pre-date { width: 160px; flex-shrink: 0; }

.money-col { position: relative; overflow: hidden; }
.money-col::before { content: ''; position: absolute; inset: 0 0 auto; height: 3px; background: var(--grad-tech); }
.calc { display: flex; flex-direction: column; gap: 12px; padding: 16px; border-radius: 14px; background: var(--card-2); border: 1px solid var(--stroke); }
.calc-title { font-family: var(--font-mono); font-size: 11px; letter-spacing: .12em; text-transform: uppercase; color: var(--muted-2); }
.bar { display: flex; gap: 2px; height: 10px; }
.seg { min-width: 0; height: 100%; }
.seg:first-child { border-radius: 4px 0 0 4px; }
.seg:last-child { border-radius: 0 4px 4px 0; }
.f1 { background: #8b5cf6; } .f2 { background: #0ea5e9; } .wk { background: #d97706; } .co { background: #059669; }
.calc-rows { display: flex; flex-direction: column; gap: 8px; font-size: 13.5px; }
.calc-rows > div { display: flex; align-items: center; gap: 8px; }
.calc-rows b { margin-left: auto; }
.calc-rows .total { padding-top: 10px; border-top: 1px dashed var(--stroke-strong); font-weight: 600; }
.calc-rows .total b { font-size: 16px; color: var(--ok-fg); }
.calc-rows .total.bad b { color: var(--bad-fg); }
.dot { width: 9px; height: 9px; border-radius: 3px; display: inline-block; flex-shrink: 0; }

.opt { border: 1px solid var(--stroke); border-radius: 14px; background: var(--card-2); transition: border-color .2s; }
.opt.on { border-color: color-mix(in srgb, var(--brand) 60%, transparent); }
.switch-row { display: flex; align-items: center; gap: 12px; padding: 13px 14px; cursor: pointer; }
.switch-row .grow { display: flex; flex-direction: column; gap: 2px; }
.opt-body { padding: 0 14px 14px; display: flex; flex-direction: column; gap: 12px; }
.switch {
  appearance: none; width: 44px; height: 26px; border-radius: 99px; background: var(--neutral-bg); border: 1px solid var(--stroke-strong);
  position: relative; cursor: pointer; transition: background .2s; flex-shrink: 0; margin: 0;
}
.switch::after { content: ''; position: absolute; top: 2px; left: 2px; width: 20px; height: 20px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.3); transition: transform .25s cubic-bezier(.16,1,.3,1); }
.switch:checked { background: var(--brand); border-color: var(--brand); }
.switch:checked::after { transform: translateX(18px); }
.segmented.full { display: flex; }
.segmented.full button { flex: 1; }

.pf-bar {
  grid-column: 1 / -1; position: sticky; bottom: 16px; z-index: 20; display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  padding: 14px 18px; border-radius: 18px; background: var(--panel); backdrop-filter: blur(18px);
  border: 1px solid var(--stroke-strong); box-shadow: var(--shadow);
}
.sum { display: flex; gap: 26px; flex-wrap: wrap; }
.sum > div { display: flex; flex-direction: column; }
.sum b { font-size: 18px; }
.err { white-space: normal; }
.actions { margin-left: auto; }

@media (max-width: 1200px) {
  .pf-grid { grid-template-columns: 1fr 1fr; }
  .money-col { grid-column: 2; grid-row: 1 / span 2; }
}
@media (max-width: 900px) {
  .pf { padding-bottom: 0; }
  .pf-grid { grid-template-columns: 1fr; }
  .money-col { grid-column: auto; grid-row: auto; }
  .pf-bar { bottom: calc(var(--tabbar-h) + var(--safe-bottom) + 8px); padding: 10px 12px; gap: 10px; flex-wrap: nowrap; }
  .hide-m { display: none !important; }
  .sum b { font-size: 16px; }
  .err { position: absolute; left: 12px; right: 12px; bottom: calc(100% + 8px); }
  .pre-date { width: 140px; }
  .people { grid-template-columns: 1fr; }
}
</style>
