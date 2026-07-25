<template>
  <div>
    <div class="row between wrap gap-12" style="margin-bottom: 20px">
      <div class="row gap-8 wrap">
        <button v-for="f in filters" :key="f.v" class="btn sm" :class="{ primary: filter === f.v }" @click="filter = f.v">
          {{ f.label }}
        </button>
      </div>
      <button class="btn primary" @click="openCreate"><Icon name="plus" :size="18" /> Новый проект</button>
    </div>

    <transition-group name="list" tag="div" class="cards">
      <div v-for="(p, i) in filtered" :key="p.id" class="proj card" @click="$router.push(`/projects/${p.id}`)">
        <div class="row between">
          <StatusBadge :status="p.status" />
          <div class="row gap-4">
            <span v-if="p.has_stages" class="badge blue">Этапы</span>
            <span v-if="p.has_monthly" class="badge amber">Ежемесячная</span>
          </div>
        </div>
        <h3 class="p-name">{{ p.name }}</h3>
        <div class="row gap-8 muted small">
          <span class="row gap-8"><Icon name="user" :size="15" /> {{ p.worker_name || p.worker_username }}</span>
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
      </div>
    </transition-group>

    <div v-if="!filtered.length" class="card center muted" style="padding: 50px">
      Проектов нет. Нажмите «Новый проект», чтобы создать первый.
    </div>

    <!-- ===== Модалка создания ===== -->
    <Modal v-model="show" eyebrow="Новый проект" title="Создание проекта" wide>
      <div v-if="!workers.length" class="badge amber" style="margin-bottom: 14px">
        Сначала создайте рабочего во вкладке «Рабочие»
      </div>

      <div class="grid-2">
        <div class="field">
          <label>Рабочий *</label>
          <select v-model="form.worker" class="select">
            <option :value="null" disabled>Выберите рабочего</option>
            <option v-for="w in workers" :key="w.id" :value="w.id">{{ w.full_name || w.username }}</option>
          </select>
        </div>
        <div class="field">
          <label>Название проекта *</label>
          <input v-model="form.name" class="input" placeholder="Напр. Интернет-магазин" />
        </div>
      </div>

      <div class="field">
        <label>Тип оплаты</label>
        <div class="row gap-16">
          <label class="check">
            <input type="checkbox" v-model="form.has_stages" />
            <span class="box"><svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
            <span>Оплата по этапам</span>
          </label>
          <label class="check">
            <input type="checkbox" v-model="form.has_monthly" />
            <span class="box"><svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
            <span>Ежемесячная оплата</span>
          </label>
        </div>
      </div>

      <!-- Разовая / Этапы -->
      <div v-if="form.has_stages" class="opt-block open">
        <div class="h3" style="margin-bottom: 12px; font-weight: 600;">Суммы по этапам</div>
        <div class="grid-3">
          <div class="field"><label>Старт, ₸</label><input v-model="form.start_amount" type="number" class="input" placeholder="100000" /></div>
          <div class="field"><label>Бета-версия, ₸</label><input v-model="form.beta_amount" type="number" class="input" placeholder="300000" /></div>
          <div class="field"><label>Сдача (Финал), ₸</label><input v-model="form.final_amount" type="number" class="input" placeholder="100000" /></div>
        </div>

        <div class="grid-2 mt-8">
          <div class="field"><label>Рабочему за бету, ₸</label><input v-model="form.worker_beta_amount" type="number" class="input" placeholder="50000" /></div>
          <div class="field"><label>Рабочему за сдачу, ₸</label><input v-model="form.worker_final_amount" type="number" class="input" placeholder="30000" /></div>
        </div>
        <div class="muted small" style="margin-top: 4px">Старт выплачивается без доли рабочего.</div>

        <!-- Распределение -->
        <div class="dist">
          <div class="dist-title muted small">Живой расчёт распределения (Суммы старт + бета + финал):</div>
          <div class="dist-grid">
            <div class="dist-item purple"><span>{{ settings.fund1_name }}</span><b class="mono">{{ money(dist.f20) }}</b></div>
            <div class="dist-item blue"><span>{{ settings.fund2_name }}</span><b class="mono">{{ money(dist.f5) }}</b></div>
            <div class="dist-item amber"><span>Рабочему (бета+сдача)</span><b class="mono">{{ money(dist.worker) }}</b></div>
            <div class="dist-item green"><span>Компании</span><b class="mono">{{ money(dist.company) }}</b></div>
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

const emit = defineEmits(['changed'])
const projects = ref([])
const workers = ref([])
const filter = ref('all')
const filters = [
  { v: 'all', label: 'Все' },
  { v: 'active', label: 'В работе' },
  { v: 'done', label: 'Завершённые' },
  { v: 'monthly', label: 'Ежемесячные' },
]

const filtered = computed(() => {
  if (filter.value === 'all') return projects.value
  if (filter.value === 'monthly') return projects.value.filter(p => p.has_monthly)
  return projects.value.filter(p => p.status === filter.value)
})

const show = ref(false)
const saving = ref(false)
const error = ref('')
const settings = ref({ fund1_name: 'Фонд 20%', fund1_rate: 20, fund2_name: 'Фонд 5%', fund2_rate: 5 })
const blank = () => ({
  worker: null, name: '', has_stages: true, has_monthly: false,
  start_amount: '', beta_amount: '', final_amount: '',
  worker_beta_amount: '', worker_final_amount: '', monthly_amount: '',
  start_date: today(), deadline_date: '', beta_date: '',
  has_server: false, server_login: '', server_password: '', server_days: '', server_amount: '', server_paid_from: 'company',
})
const form = reactive(blank())

function today() { return new Date().toISOString().slice(0, 10) }

const totalStagesNum = computed(() => (Number(form.start_amount) || 0) + (Number(form.beta_amount) || 0) + (Number(form.final_amount) || 0))
const dist = computed(() => {
  // как на бэке: фонды считаются с суммы этапов по ставкам из настроек,
  // доля рабочего — фиксированные суммы за бету и сдачу (старт без доли)
  const a = totalStagesNum.value
  const f20 = a * (Number(settings.value.fund1_rate) || 0) / 100
  const f5 = a * (Number(settings.value.fund2_rate) || 0) / 100
  const worker = (Number(form.worker_beta_amount) || 0) + (Number(form.worker_final_amount) || 0)
  return { f20, f5, worker, company: a - f20 - f5 - worker }
})

const valid = computed(() => form.worker && form.name && form.start_date && form.deadline_date)

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
    for (const k of ['start_amount', 'beta_amount', 'final_amount', 'worker_beta_amount', 'worker_final_amount', 'monthly_amount', 'server_days', 'server_amount']) {
      if (payload[k] === '') payload[k] = null
    }
    if (!payload.beta_date) payload.beta_date = null
    await api.post('/projects/', payload)
    show.value = false
    await load()
    emit('changed')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Проверьте поля формы'
  } finally {
    saving.value = false
  }
}

async function load() {
  const [p, w, s] = await Promise.all([api.get('/projects/'), api.get('/workers/'), api.get('/settings/')])
  projects.value = p.data
  workers.value = w.data
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
.p-foot { display: flex; justify-content: space-between; padding-top: 4px; border-top: 1px solid var(--stroke); }

.seg { display: flex; gap: 6px; background: var(--input-bg); padding: 5px; border-radius: 12px; }
.seg button { flex: 1; padding: 10px; border-radius: 9px; border: none; background: transparent; color: var(--muted); font-weight: 600; cursor: pointer; transition: all .2s; font-size: 13px; }
.seg button.on { background: var(--brand); color: #fff; }

.opt-block { margin-top: 14px; padding: 16px; border-radius: 14px; border: 1px solid var(--stroke); background: var(--card-2); transition: border-color .2s; }
.opt-block.open { border-color: var(--brand); }
.opt-body { margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--stroke); display: flex; flex-direction: column; gap: 4px; }

.dist { margin-top: 12px; padding: 14px; border-radius: 12px; background: var(--info-bg); border: 1px solid transparent; }
.dist-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 10px; }
.dist-item { display: flex; justify-content: space-between; padding: 10px 12px; border-radius: 10px; background: var(--card); font-size: 13px; border-left: 3px solid; }
.dist-item.purple { border-color: #4f46e5; } .dist-item.blue { border-color: #0284c7; }
.dist-item.amber { border-color: #d97706; } .dist-item.green { border-color: #059669; }
</style>
