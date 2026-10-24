<template>
  <div class="wshell">
    <CabinetHeader subtitle="кабинет рабочего" role-label="Рабочий" @tick="loadData" />

    <div class="wbody">
      <div class="hero card animate-in">
        <div class="eyebrow">Ваш заработок</div>
        <div class="hero-val mono">{{ money(data.total_earned) }}</div>
        <div class="muted">Всего начислено вам с оплат клиентов по вашим проектам</div>
      </div>

      <div class="row between wrap gap-12 mt-24" style="margin-bottom: 14px">
        <h2 class="h2">Мои проекты</h2>
        <div class="row gap-8">
          <button v-for="t in tabs" :key="t.v" class="btn sm" :class="{ primary: tab === t.v }" @click="setTab(t.v)">
            {{ t.label }} <span class="tab-count">{{ t.count }}</span>
          </button>
        </div>
      </div>

      <FilterBar v-if="data.projects?.length" v-model:search="q" v-model:from="dateFrom" v-model:to="dateTo" dates
        date-label="Дедлайн" placeholder="Название проекта, комментарий…" :count="tabProjects.length" :total="tabAll.length" />

      <transition-group name="list" tag="div" class="cards">
        <div v-for="p in visibleProjects" :key="p.id" class="pcard card">
          <div class="row between">
            <StatusBadge :status="p.status" />
            <div class="row gap-4">
              <span v-if="p.has_monthly" class="badge amber">Ежемесячная</span>
            </div>
          </div>
          <h3 class="p-name">{{ p.name }}</h3>
          <div v-if="p.client_name || p.client_phone" class="muted small row gap-8"><Icon name="phone" :size="14" /> Клиент: {{ [p.client_name, p.client_phone].filter(Boolean).join(' · ') }}</div>

          <div class="earn" v-if="p.has_price">
            <div class="row between">
              <span class="muted small">Ваша сумма за проект</span>
              <span v-if="p.worker_amount" class="mono">{{ money(p.worker_amount) }}</span>
              <span v-else class="muted small">пока не указана</span>
            </div>
            <div class="row between" style="margin-top: 8px; border-top: 1px solid var(--stroke); padding-top: 8px">
              <span class="muted small">Начислено вам</span>
              <span class="mono" style="font-size: 16px; font-weight: 800; color: var(--warn-fg)">{{ money(p.totals.worker) }}</span>
            </div>
          </div>
          <div class="earn" v-if="p.has_monthly && !p.has_price">
            <div class="muted small">Помесячный проект</div>
            <div class="muted small">Оплата вашей работы обсуждается отдельно.</div>
          </div>

          <div class="dates">
            <div><span class="muted small">Старт</span><b>{{ formatDate(p.start_date) }}</b></div>
            <div><span class="muted small">Дедлайн</span><b>{{ formatDate(p.deadline_date) }}</b></div>
            <div><span class="muted small">Сдал</span><b>{{ p.finished_date ? formatDate(p.finished_date) : '—' }}</b></div>
          </div>

          <div class="deadline-line">
            <DeadlineBadge :status="p.deadline_status" />
          </div>

          <!-- сдача идёт через проверку: проверит любой тестировщик -->
          <div v-if="p.status === 'active' || p.review_status !== 'none'" class="review-line" :class="p.review_status">
            <div class="row between gap-8 wrap">
              <span class="muted small row gap-8"><Icon name="check-circle" :size="14" />
                <template v-if="p.reviewer_name">Проверил: <b class="strong">{{ p.reviewer_name }}</b></template>
                <template v-else>Проверка тестировщиком</template>
              </span>
              <ReviewBadge :status="p.review_status" />
            </div>
            <div v-if="p.review_status === 'returned' && lastReturn(p)" class="return-note">
              <div class="muted small">Замечания тестировщика</div>
              <div class="return-text">{{ lastReturn(p).text }}</div>
            </div>
            <button class="btn sm" :class="canSubmit(p) ? 'primary' : 'ghost'" @click="openReview(p)">
              <Icon :name="canSubmit(p) ? 'send' : 'message'" :size="14" />
              {{ canSubmit(p) ? (p.review_status === 'returned' ? 'Исправил — отправить снова' : 'Отправить на проверку') : 'Переписка' }}
              <span v-if="p.comments.length" class="tab-count">{{ p.comments.length }}</span>
            </button>
          </div>
          <button v-else-if="p.comments.length" class="btn sm ghost" @click="openReview(p)">
            <Icon name="message" :size="14" /> Комментарии <span class="tab-count">{{ p.comments.length }}</span>
          </button>

          <div v-if="p.servers.length" class="srv-line muted small row gap-8">
            <Icon name="server" :size="14" /> Сервер до {{ formatDate(p.servers[0].expiry_date) }}
            <span class="badge" :class="p.servers[0].days_left <= 7 ? 'amber' : 'green'" style="margin-left: 6px">{{ p.servers[0].days_left }} дн.</span>
          </div>
        </div>
      </transition-group>

      <div v-if="hiddenCount" class="more-row">
        <button class="btn ghost more-btn" :class="{ open: expanded }" @click="expanded = !expanded">
          <Icon name="chevron-down" :size="18" class="chev" />
          {{ expanded ? 'Свернуть' : `Показать ещё ${hiddenCount}` }}
        </button>
      </div>

      <div v-if="!data.projects?.length" class="card center muted" style="padding: 50px">
        Пока вам не назначено ни одного проекта
      </div>
      <div v-else-if="!tabProjects.length" class="card center muted" style="padding: 50px">
        {{ tabAll.length ? 'По фильтрам ничего не найдено' : (tab === 'active' ? 'Сейчас нет проектов в работе' : 'Завершённых проектов пока нет') }}
      </div>
    </div>

    <Modal v-model="reviewModal" eyebrow="Проверка проекта" :title="current?.name" wide>
      <ReviewThread v-if="current" :project="current" @update="onUpdate" />
    </Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api, { money, formatDate } from '../../api'
import CabinetHeader from '../../components/CabinetHeader.vue'
import Modal from '../../components/Modal.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import Icon from '../../components/Icon.vue'
import DeadlineBadge from '../../components/DeadlineBadge.vue'
import ReviewBadge from '../../components/ReviewBadge.vue'
import ReviewThread from '../../components/ReviewThread.vue'
import FilterBar from '../../components/FilterBar.vue'
import { textMatch, inRange } from '../../filters'

const data = ref({ projects: [], total_earned: 0 })

const VISIBLE_LIMIT = 3
const expanded = ref(false)

// «В работе» — по умолчанию; завершённые и отменённые уходят во вторую вкладку
const tab = ref('active')
const activeProjects = computed(() => (data.value.projects || []).filter(p => p.status === 'active'))
const closedProjects = computed(() => {
  const all = data.value.projects || []
  return [...all.filter(p => p.status === 'done'), ...all.filter(p => p.status === 'cancelled')]
})
const tabs = computed(() => [
  { v: 'active', label: 'В работе', count: activeProjects.value.length },
  { v: 'closed', label: 'Завершённые', count: closedProjects.value.length },
])
const tabAll = computed(() => (tab.value === 'active' ? activeProjects.value : closedProjects.value))

// поиск по названию и переписке, период по дедлайну
const q = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const tabProjects = computed(() => tabAll.value.filter(p =>
  textMatch(q.value, p.name, p.reviewer_name, ...p.comments.map(c => c.text)) &&
  inRange(p.deadline_date, dateFrom.value, dateTo.value)))
function setTab(v) { tab.value = v; expanded.value = false }

const visibleProjects = computed(() =>
  expanded.value ? tabProjects.value : tabProjects.value.slice(0, VISIBLE_LIMIT)
)
const hiddenCount = computed(() => Math.max(0, tabProjects.value.length - VISIBLE_LIMIT))

async function loadData() { data.value = (await api.get('/worker/dashboard/')).data }

// ----- проверка тестировщиком -----
const canSubmit = (p) => p.status === 'active' && ['none', 'returned'].includes(p.review_status)
const lastReturn = (p) => [...p.comments].reverse().find(c => c.kind === 'return')

const reviewModal = ref(false)
const currentId = ref(null)
const current = computed(() => (data.value.projects || []).find(p => p.id === currentId.value) || null)
function openReview(p) { currentId.value = p.id; reviewModal.value = true }
function onUpdate(fresh) {
  const i = data.value.projects.findIndex(p => p.id === fresh.id)
  if (i >= 0) data.value.projects[i] = fresh
}

onMounted(loadData)
</script>

<style scoped>
.wshell { min-height: 100vh; }
.strong { color: var(--text); }
.review-line { display: flex; flex-direction: column; gap: 10px; padding: 12px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); }
.review-line.returned { border-color: var(--c-red); }
.review-line.review { border-color: var(--brand); }
.return-note { padding: 10px 12px; border-radius: 10px; background: var(--bad-bg); }
.return-text { margin-top: 4px; font-size: 14px; white-space: pre-wrap; word-break: break-word; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.wbody { max-width: 1100px; margin: 0 auto; padding: 28px 32px 60px; }
.hero { position: relative; overflow: hidden; }
.hero::after { content: ''; position: absolute; inset: 0; background: radial-gradient(300px 160px at 90% -10%, rgba(37,99,235,.18), transparent 70%); pointer-events: none; }
.hero-val { font-size: 44px; font-weight: 800; letter-spacing: -.03em; margin: 8px 0; color: var(--brand); }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; position: relative; }
.pcard { transition: transform .25s cubic-bezier(.16,1,.3,1), border-color .25s, box-shadow .25s; }
.pcard:hover { transform: translateY(-3px); border-color: var(--stroke-strong); box-shadow: var(--shadow); }
.pcard { display: flex; flex-direction: column; gap: 12px; }
.p-name { margin: 0; font-size: 18px; font-weight: 700; }
.earn { padding: 14px; border-radius: 12px; background: var(--input-bg); display: flex; flex-direction: column; gap: 4px; }
.dates { display: flex; justify-content: space-between; }
.dates div { display: flex; flex-direction: column; gap: 3px; }
.tab-count { opacity: .7; font-weight: 700; margin-left: 2px; }
.more-row { display: flex; justify-content: center; margin-top: 20px; }
.more-btn { border-radius: 999px; padding: 11px 22px; }
.more-btn:hover { border-color: var(--brand); color: var(--brand); }
.more-btn .chev { transition: transform .35s cubic-bezier(.16,1,.3,1); }
.more-btn.open .chev { transform: rotate(180deg); }
.deadline-line { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-top: 10px; border-top: 1px solid var(--stroke); flex-wrap: wrap; }
.srv-line { padding-top: 10px; border-top: 1px solid var(--stroke); }
</style>
