<template>
  <div>
    <div class="row between wrap gap-12" style="margin-bottom: 20px">
      <div class="row gap-8 wrap">
        <button v-for="f in filters" :key="f.v" class="btn sm" :class="{ primary: filter === f.v }" @click="filter = f.v">
          {{ f.label }} <span class="f-count">{{ f.count }}</span>
        </button>
      </div>
      <button class="btn primary" @click="openCreate"><Icon name="plus" :size="18" /> Новый проект</button>
    </div>

    <FilterBar v-model:search="q" v-model:from="dateFrom" v-model:to="dateTo" dates :date-label="dateFields[dateField]"
      placeholder="Название, рабочий, тестировщик…" :count="filtered.length" :total="tabTotal"
      :extra-active="!!workerFilter" @reset="workerFilter = ''">
      <select v-model="workerFilter" class="select f-select">
        <option value="">Все рабочие</option>
        <option v-for="w in workers" :key="w.id" :value="w.id">{{ w.full_name || w.username }}</option>
      </select>
      <select v-model="dateField" class="select f-select" title="По какой дате фильтровать период">
        <option v-for="(label, k) in dateFields" :key="k" :value="k">Период по: {{ label.toLowerCase() }}</option>
      </select>
      <select v-model="sort" class="select f-select">
        <option v-for="(s, k) in sorts" :key="k" :value="k">{{ s.label }}</option>
      </select>
    </FilterBar>

    <transition-group name="list" tag="div" class="cards">
      <div v-for="(p, i) in filtered" :key="p.id" class="proj card" @click="$router.push(`/projects/${p.id}`)">
        <div class="row between">
          <StatusBadge :status="p.status" />
          <div class="row gap-4">
            <span v-if="p.has_monthly" class="badge amber">Ежемесячная</span>
          </div>
        </div>
        <h3 class="p-name">{{ p.name }}</h3>
        <div class="row gap-16 wrap muted small">
          <span class="row gap-8"><Icon name="user" :size="15" /> {{ p.worker_name || p.worker_username }}</span>
          <span v-if="p.client_name || p.client_phone" class="row gap-8"><Icon name="phone" :size="14" /> {{ [p.client_name, p.client_phone].filter(Boolean).join(' · ') }}</span>
        </div>
        <div v-if="p.review_status !== 'none'" class="row between gap-8 wrap muted small">
          <span class="row gap-8"><Icon name="check-circle" :size="15" /> {{ p.reviewer_name || 'Проверка' }}</span>
          <ReviewBadge :status="p.review_status" />
        </div>

        <div class="p-money">
          <div>
            <div class="muted small">Получено</div>
            <div class="mono" style="font-weight: 700">{{ money(p.totals.received) }}</div>
          </div>
          <div>
            <div class="muted small">Стоимость</div>
            <div class="mono" style="font-weight: 700">
              {{ money(p.total_price) }}
            </div>
            <div v-if="p.has_monthly" class="muted small mt-4">+ {{ money(p.monthly_amount) }} / мес</div>
          </div>
        </div>

        <div class="p-foot muted small">
          <span class="row gap-8"><Icon name="play" :size="14" /> {{ formatDate(p.start_date) }}</span>
          <span class="row gap-8"><Icon name="flag" :size="14" /> {{ formatDate(p.deadline_date) }}</span>
        </div>

        <button v-if="p.status !== 'cancelled'" class="btn sm danger" @click.stop="askCancel(p)">
          <Icon name="close" :size="15" /> Отменить проект
        </button>
        <button v-else class="btn sm ghost" @click.stop="setStatus(p, 'active')">
          <Icon name="renew" :size="15" /> Вернуть в работу
        </button>
      </div>
    </transition-group>

    <div v-if="!filtered.length" class="card center muted" style="padding: 50px">
      {{ tabTotal ? 'По фильтрам ничего не найдено — измените поиск или нажмите «Сбросить».' : emptyText[filter] }}
    </div>

    <!-- ===== Подтверждение отмены ===== -->
    <Modal v-model="cancelModal" eyebrow="Отмена" title="Отменить проект?">
      <p class="muted">
        Проект <b style="color: var(--text)">«{{ cancelTarget?.name }}»</b> получит статус «Отменён» и пропадёт из списка.
        Платежи по нему останутся в финансах. Вернуть проект можно во вкладке «Отменённые».
      </p>
      <div class="row between mt-16">
        <button class="btn ghost" @click="cancelModal = false">Не отменять</button>
        <button class="btn danger" :disabled="cancelBusy" @click="confirmCancel">
          <span v-if="cancelBusy" class="spinner"></span><span v-else>Отменить проект</span>
        </button>
      </div>
    </Modal>

    <!-- ===== Модалка создания ===== -->
    <Modal v-model="show" eyebrow="Новый проект" title="Создание проекта" wide>
      <div v-if="!workers.length" class="badge amber" style="margin-bottom: 14px">
        Сначала создайте рабочего во вкладке «Пользователи»
      </div>

      <div class="field">
        <label>Название проекта *</label>
        <input v-model="form.name" class="input" placeholder="Напр. Интернет-магазин" />
      </div>
      <div class="field">
        <label>Рабочий *</label>
        <select v-model="form.worker" class="select">
          <option :value="null" disabled>Выберите рабочего</option>
          <option v-for="w in workers" :key="w.id" :value="w.id">{{ w.full_name || w.username }}</option>
        </select>
        <span class="muted small">Проверять проект сможет любой тестировщик — назначать его не нужно.</span>
      </div>
      <div class="grid-2">
        <div class="field"><label>Клиент</label><input v-model="form.client_name" class="input" placeholder="Имя или компания" /></div>
        <div class="field"><label>Номер клиента</label><input v-model="form.client_phone" class="input" type="tel" placeholder="+7 700 000 00 00" /></div>
      </div>

      <div class="field">
        <label>Тип оплаты</label>
        <div class="row gap-16">
          <label class="check">
            <input type="checkbox" v-model="form.has_price" />
            <span class="box"><svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
            <span>Оплата за проект</span>
          </label>
          <label class="check">
            <input type="checkbox" v-model="form.has_monthly" />
            <span class="box"><svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
            <span>Ежемесячная оплата</span>
          </label>
        </div>
      </div>

      <!-- Оплата за проект: одна сумма -->
      <div v-if="form.has_price" class="opt-block open">
        <div class="row between wrap gap-8" style="margin-bottom: 12px">
          <div class="h3" style="font-weight: 600;">Сумма проекта</div>
          <span class="muted small">Необязательно — можно указать или изменить позже внутри проекта</span>
        </div>
        <div class="grid-2">
          <div class="field"><label>Сумма проекта, ₸</label><input v-model="form.price" type="number" min="0" class="input" placeholder="500000" /></div>
          <div class="field"><label>Рабочему, ₸</label><input v-model="form.worker_amount" type="number" min="0" class="input" placeholder="можно оставить пустым" /></div>
        </div>
        <div class="muted small" style="margin-top: 4px">Клиент может платить частями — рабочий получает свою долю с каждой оплаты.</div>

        <!-- Распределение -->
        <div class="dist">
          <div class="dist-title muted small">Живой расчёт распределения (со всей суммы проекта):</div>
          <div class="dist-grid">
            <div class="dist-item purple">
              <span>{{ settings.fund1_name }}</span>
              <label class="rate"><input v-model="form.fund1_rate" type="number" min="0" max="100" step="0.5" class="rate-input mono" /> %</label>
              <b class="mono">{{ money(dist.f20) }}</b>
            </div>
            <div class="dist-item blue">
              <span>{{ settings.fund2_name }}</span>
              <label class="rate"><input v-model="form.fund2_rate" type="number" min="0" max="100" step="0.5" class="rate-input mono" /> %</label>
              <b class="mono">{{ money(dist.f5) }}</b>
            </div>
            <div class="dist-item amber"><span>Рабочему</span><b class="mono">{{ money(dist.worker) }}</b></div>
            <div class="dist-item green"><span>Компании</span><b class="mono">{{ money(dist.company) }}</b></div>
          </div>
          <div class="row between wrap gap-8 muted small" style="margin-top: 10px">
            <span v-if="!ratesValid" style="color: var(--bad-fg)">Проценты: от 0 до 100, в сумме не больше 100.</span>
            <span v-else-if="dist.company < 0" style="color: var(--bad-fg)">Компания уходит в минус: фонды и рабочий забирают больше суммы проекта.</span>
            <span v-else-if="ratesChanged">Свои проценты — только для этого проекта.</span>
            <span v-else>Проценты из настроек. Можно изменить для этого проекта.</span>
            <button v-if="ratesChanged" type="button" class="btn sm ghost" @click="resetRates">Как в настройках</button>
          </div>
        </div>
      </div>

      <!-- Ежемесячная -->
      <div v-if="form.has_monthly" class="opt-block open">
        <div class="h3" style="margin-bottom: 12px; font-weight: 600;">Ежемесячная оплата</div>
        <div class="field">
          <label>Оплата в месяц, ₸</label>
          <input v-model="form.monthly_amount" type="number" class="input" placeholder="150000" />
          <span class="muted small">Доля рабочего при помесячной оплате не выделяется.</span>
        </div>
      </div>

      <!-- Даты -->
      <div class="grid-3 mt-8">
        <div class="field"><label>Начало проекта</label><input v-model="form.start_date" type="date" class="input" /></div>
        <div class="field"><label>Дедлайн (сдача)</label><input v-model="form.deadline_date" type="date" class="input" /></div>
        <div class="field"><label>Показ бета-версии</label><input v-model="form.beta_date" type="date" class="input" /></div>
      </div>

      <!-- Сервер -->
      <div class="opt-block" :class="{ open: form.has_server }">
        <label class="check">
          <input type="checkbox" v-model="form.has_server" />
          <span class="box"><svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          <span><b>Куплен сервер</b> для этого проекта</span>
        </label>
        <transition name="pop">
          <div v-if="form.has_server" class="opt-body">
            <div class="grid-2">
              <div class="field"><label>Логин сервера</label><input v-model="form.server_login" class="input" placeholder="root" /></div>
              <div class="field"><label>Пароль сервера</label><input v-model="form.server_password" class="input" placeholder="••••••" /></div>
            </div>
            <div class="field">
              <label>Куплен на срок</label>
              <div class="row gap-8 wrap">
                <button class="btn sm" :class="{ primary: form.server_days == 30 }" @click="form.server_days = 30">Месяц</button>
                <button class="btn sm" :class="{ primary: form.server_days == 365 }" @click="form.server_days = 365">Год</button>
                <input v-model="form.server_days" type="number" class="input" style="max-width: 130px" placeholder="дней" />
              </div>
            </div>
            <div class="grid-2">
              <div class="field"><label>Стоимость сервера, ₸</label><input v-model="form.server_amount" type="number" class="input" placeholder="45000" /></div>
              <div class="field">
                <label>Оплачено из</label>
                <select v-model="form.server_paid_from" class="select">
                  <option value="company">Деньги компании</option>
                  <option value="fund20">Фонд 20%</option>
                  <option value="fund5">Фонд 5%</option>
                </select>
              </div>
            </div>
          </div>
        </transition>
      </div>



      <transition name="pop">
        <div v-if="error" class="badge red" style="margin-top: 10px">{{ error }}</div>
      </transition>

      <div class="row between mt-16">
        <button class="btn ghost" @click="show = false">Отмена</button>
        <button class="btn primary" :disabled="saving || !valid" @click="save">
          <span v-if="saving" class="spinner"></span>
          <span v-else>Создать проект</span>
        </button>
      </div>
    </Modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api, { money, formatDate } from '../../api'
import Modal from '../../components/Modal.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import Icon from '../../components/Icon.vue'
import ReviewBadge from '../../components/ReviewBadge.vue'
import FilterBar from '../../components/FilterBar.vue'
import { textMatch, inRange } from '../../filters'

const emit = defineEmits(['changed'])
const projects = ref([])
const workers = ref([])
// каждый проект живёт в своей вкладке: в работе / завершённые / отменённые;
// «Ежемесячные» — все не отменённые проекты с ежемесячной оплатой
const filter = ref('active')
const byFilter = {
  active: p => p.status === 'active',
  done: p => p.status === 'done',
  monthly: p => p.has_monthly && p.status !== 'cancelled',
  cancelled: p => p.status === 'cancelled',
}
const filters = computed(() => [
  { v: 'active', label: 'В работе' },
  { v: 'done', label: 'Завершённые' },
  { v: 'monthly', label: 'Ежемесячные' },
  { v: 'cancelled', label: 'Отменённые' },
].map(f => ({ ...f, count: searched.value.filter(byFilter[f.v]).length })))

// ----- поиск, рабочий, период, сортировка -----
const q = ref('')
const workerFilter = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const dateField = ref('start_date')
const dateFields = { start_date: 'Начало', deadline_date: 'Дедлайн', finished_date: 'Сдача', created_at: 'Создание' }
const sorts = {
  new: { label: 'Сначала новые', fn: (a, b) => b.created_at.localeCompare(a.created_at) },
  old: { label: 'Сначала старые', fn: (a, b) => a.created_at.localeCompare(b.created_at) },
  deadline: { label: 'Ближайший дедлайн', fn: (a, b) => a.deadline_date.localeCompare(b.deadline_date) },
  name: { label: 'По названию', fn: (a, b) => a.name.localeCompare(b.name, 'ru') },
}
const sort = ref('new')

// поиск и фильтры применяются ко всем вкладкам — счётчики вкладок показывают найденное
const searched = computed(() => projects.value.filter(p =>
  textMatch(q.value, p.name, p.worker_name, p.worker_username, p.reviewer_name, p.client_name, p.client_phone) &&
  (!workerFilter.value || p.worker === workerFilter.value) &&
  inRange(p[dateField.value], dateFrom.value, dateTo.value)
))
const tabTotal = computed(() => projects.value.filter(byFilter[filter.value]).length)
const filtered = computed(() => searched.value.filter(byFilter[filter.value]).sort(sorts[sort.value].fn))
const emptyText = {
  active: 'Проектов в работе нет. Нажмите «Новый проект», чтобы создать.',
  done: 'Завершённых проектов пока нет.',
  monthly: 'Проектов с ежемесячной оплатой нет.',
  cancelled: 'Отменённых проектов нет.',
}

const cancelModal = ref(false)
const cancelTarget = ref(null)
const cancelBusy = ref(false)

function askCancel(p) { cancelTarget.value = p; cancelModal.value = true }

async function setStatus(p, status) {
  await api.patch(`/projects/${p.id}/`, { status })
  await load()
  emit('changed')
}

async function confirmCancel() {
  cancelBusy.value = true
  try {
    await setStatus(cancelTarget.value, 'cancelled')
    cancelModal.value = false
  } finally { cancelBusy.value = false }
}

const show = ref(false)
const saving = ref(false)
const error = ref('')
const settings = ref({ fund1_name: 'Фонд 20%', fund1_rate: 20, fund2_name: 'Фонд 5%', fund2_rate: 5 })
const blank = () => ({
  worker: null, name: '', client_name: '', client_phone: '', has_price: true, has_monthly: false,
  price: '', worker_amount: '', monthly_amount: '',
  fund1_rate: Number(settings.value.fund1_rate), fund2_rate: Number(settings.value.fund2_rate),
  start_date: today(), deadline_date: '', beta_date: '',
  has_server: false, server_login: '', server_password: '', server_days: '', server_amount: '', server_paid_from: 'company',
})
const form = reactive(blank())

function today() { return new Date().toISOString().slice(0, 10) }

const dist = computed(() => {
  // как на бэке: фонды — проценты от суммы проекта, рабочему — его сумма, остальное компании
  const a = Number(form.price) || 0
  const f20 = a * (Number(form.fund1_rate) || 0) / 100
  const f5 = a * (Number(form.fund2_rate) || 0) / 100
  const worker = Number(form.worker_amount) || 0
  return { f20, f5, worker, company: a - f20 - f5 - worker }
})

// ставки фондов: в форме стоят значения из настроек, их можно поменять для проекта
const sameRate = (a, b) => a !== '' && Number(a) === Number(b)
const ratesChanged = computed(() =>
  !sameRate(form.fund1_rate, settings.value.fund1_rate) || !sameRate(form.fund2_rate, settings.value.fund2_rate))
const ratesValid = computed(() => {
  const r1 = Number(form.fund1_rate) || 0, r2 = Number(form.fund2_rate) || 0
  return r1 >= 0 && r2 >= 0 && r1 + r2 <= 100
})
function resetRates() {
  form.fund1_rate = Number(settings.value.fund1_rate)
  form.fund2_rate = Number(settings.value.fund2_rate)
}

const valid = computed(() => form.worker && form.name && form.start_date && form.deadline_date && (!form.has_price || ratesValid.value))

function openCreate() {
  Object.assign(form, blank())
  error.value = ''
  show.value = true
}

async function save() {
  error.value = ''
  saving.value = true
  try {
    const payload = { ...form }
    // очистим пустые числовые/даты
    // пустые суммы — «не указано» (null); их можно добавить позже внутри проекта
    for (const k of ['price', 'worker_amount', 'monthly_amount', 'server_days', 'server_amount']) {
      if (payload[k] === '') payload[k] = null
    }
    if (!form.has_price) { payload.price = null; payload.worker_amount = null }
    if (!payload.beta_date) payload.beta_date = null
    // не меняли проценты — проект следует общим настройкам (null); пустое поле = 0%
    for (const k of ['fund1_rate', 'fund2_rate']) {
      if (!form.has_price || sameRate(form[k], settings.value[k])) payload[k] = null
      else payload[k] = Number(form[k]) || 0
    }
    await api.post('/projects/', payload)
    show.value = false
    await load()
    emit('changed')
  } catch (e) {
    const d = e.response?.data || {}
    // DRF отдаёт detail строкой или списком, а ошибки полей — по именам полей
    const first = Array.isArray(d.detail) ? d.detail[0] : d.detail
    const field = Object.keys(d).find(k => k !== 'detail')
    error.value = first || (field ? `${field}: ${[].concat(d[field])[0]}` : 'Проверьте поля формы')
  } finally {
    saving.value = false
  }
}

async function load() {
  const [p, u, s] = await Promise.all([api.get('/projects/'), api.get('/users/'), api.get('/settings/')])
  projects.value = p.data
  workers.value = u.data.filter(x => x.roles.includes('worker'))
  settings.value = s.data
}
onMounted(load)
</script>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; position: relative; }
.proj { cursor: pointer; transition: transform .2s, border-color .2s, box-shadow .2s; display: flex; flex-direction: column; gap: 12px; }
.proj:hover { transform: translateY(-4px); border-color: var(--stroke-strong); box-shadow: var(--shadow); }
.p-name { margin: 0; font-size: 18px; font-weight: 700; letter-spacing: -.01em; }
.p-money { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 14px; background: var(--input-bg); border-radius: 12px; }
.f-count { opacity: .7; font-weight: 700; margin-left: 2px; }
.p-foot { display: flex; justify-content: space-between; padding-top: 4px; border-top: 1px solid var(--stroke); }

.seg { display: flex; gap: 6px; background: var(--input-bg); padding: 5px; border-radius: 12px; }
.seg button { flex: 1; padding: 10px; border-radius: 9px; border: none; background: transparent; color: var(--muted); font-weight: 600; cursor: pointer; transition: all .2s; font-size: 13px; }
.seg button.on { background: var(--brand); color: #fff; }

.opt-block { margin-top: 14px; padding: 16px; border-radius: 14px; border: 1px solid var(--stroke); background: var(--card-2); transition: border-color .2s; }
.opt-block.open { border-color: var(--brand); }
.opt-body { margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--stroke); display: flex; flex-direction: column; gap: 4px; }

.dist { margin-top: 12px; padding: 14px; border-radius: 12px; background: var(--info-bg); border: 1px solid transparent; }
.dist-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
.dist-item { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 10px; background: var(--card); font-size: 13px; border-left: 3px solid; }
.dist-item b { margin-left: auto; white-space: nowrap; }
.rate { display: inline-flex; align-items: center; gap: 4px; color: var(--muted); }
.rate-input { width: 58px; padding: 5px 6px; border-radius: 8px; border: 1px solid var(--stroke-strong); background: var(--input-bg); color: var(--text); font-size: 13px; font-weight: 700; text-align: right; outline: none; transition: border-color .2s; }
.rate-input:focus { border-color: var(--brand); }
.dist-item.purple { border-color: #4f46e5; } .dist-item.blue { border-color: #0284c7; }
.dist-item.amber { border-color: #d97706; } .dist-item.green { border-color: #059669; }
</style>
