<template>
  <div class="wshell">
    <div class="wbody">
      <div class="stats">
        <div v-for="s in stats" :key="s.v" class="stat card animate-in" :class="{ on: tab === s.v }" @click="setTab(s.v)">
          <div class="muted small">{{ s.label }}</div>
          <div class="stat-val mono" :style="{ color: s.color }">{{ s.count }}</div>
          <div class="muted small">{{ s.hint }}</div>
        </div>
      </div>

      <div class="row between wrap gap-12 mt-24" style="margin-bottom: 14px">
        <h2 class="h2">{{ stats.find(s => s.v === tab)?.title }}</h2>
      </div>

      <FilterBar v-model:search="q" v-model:from="dateFrom" v-model:to="dateTo" dates date-label="Дедлайн"
        placeholder="Проект, рабочий, текст комментария…" :count="tabProjects.length" :total="tabAll.length"
        :extra-active="!!workerFilter" @reset="workerFilter = ''">
        <select v-if="workerOptions.length > 1" v-model="workerFilter" class="select f-select">
          <option value="">Все рабочие</option>
          <option v-for="w in workerOptions" :key="w.id" :value="w.id">{{ w.name }}</option>
        </select>
      </FilterBar>

      <transition-group name="list" tag="div" class="cards">
        <div v-for="p in visibleProjects" :key="p.id" class="pcard card" @click="open(p)">
          <div class="row between">
            <ReviewBadge :status="p.review_status" />
            <StatusBadge v-if="p.status !== 'active'" :status="p.status" />
          </div>
          <h3 class="p-name">{{ p.name }}</h3>
          <div class="muted small row gap-8"><Icon name="user" :size="15" /> {{ p.worker_name || p.worker_username }}</div>

          <div class="dates">
            <div><span class="muted small">Старт</span><b>{{ formatDate(p.start_date) }}</b></div>
            <div><span class="muted small">Бета</span><b>{{ formatDate(p.beta_date) }}</b></div>
            <div><span class="muted small">Дедлайн</span><b>{{ formatDate(p.deadline_date) }}</b></div>
          </div>

          <div v-if="lastComment(p)" class="last">
            <div class="muted small">{{ lastComment(p).author_name }} · {{ lastComment(p).kind_display }}</div>
            <div class="last-text">{{ lastComment(p).text || '—' }}</div>
          </div>

          <div class="foot">
            <DeadlineBadge :status="p.deadline_status" />
            <button class="btn sm" :class="p.review_status === 'review' ? 'primary' : 'ghost'" @click.stop="open(p)">
              <Icon :name="p.review_status === 'review' ? 'check-circle' : 'message'" :size="15" />
              {{ p.review_status === 'review' ? 'Проверить' : 'Открыть' }}
              <span v-if="p.comments.length" class="tab-count">{{ p.comments.length }}</span>
            </button>
          </div>
        </div>
      </transition-group>

      <div v-if="hiddenCount" class="more-row">
        <button class="btn ghost more-btn" :class="{ open: expanded }" @click="expanded = !expanded">
          <Icon name="chevron-down" :size="18" class="chev" />
          {{ expanded ? 'Свернуть' : `Показать ещё ${hiddenCount}` }}
        </button>
      </div>

      <div v-if="loaded && !tabProjects.length" class="card center muted" style="padding: 50px">
        {{ !projects.length ? 'Проектов пока нет' : (tabAll.length ? 'По фильтрам ничего не найдено' : emptyText[tab]) }}
      </div>
    </div>

    <Modal v-model="modal" eyebrow="Проверка проекта" :title="current?.name" wide>
      <ReviewThread v-if="current" :project="current" @update="onUpdate" />
    </Modal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api, { formatDate } from '../../api'
import { useAuth } from '../../stores/auth'
import Modal from '../../components/Modal.vue'
import Icon from '../../components/Icon.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import ReviewBadge from '../../components/ReviewBadge.vue'
import ReviewThread from '../../components/ReviewThread.vue'
import DeadlineBadge from '../../components/DeadlineBadge.vue'
import FilterBar from '../../components/FilterBar.vue'
import { textMatch, inRange } from '../../filters'

const auth = useAuth()
const projects = ref([])
const loaded = ref(false)
const tab = ref('review')

// ----- поиск и фильтры -----
const q = ref('')
const workerFilter = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const workerOptions = computed(() => {
  const map = new Map(projects.value.map(p => [p.worker, p.worker_name || p.worker_username]))
  return [...map].map(([id, name]) => ({ id, name }))
})
const matches = (p) =>
  textMatch(q.value, p.name, p.worker_name, p.worker_username, ...p.comments.map(c => c.text)) &&
  (!workerFilter.value || p.worker === workerFilter.value) &&
  inRange(p.deadline_date, dateFrom.value, dateTo.value)

const of = (...statuses) => projects.value.filter(p => statuses.includes(p.review_status))
const stats = computed(() => [
  { v: 'review', label: 'На проверке', title: 'Ждут проверки', hint: 'примет или вернёт тот, кто первый', color: 'var(--brand)', count: of('review').length },
  { v: 'worker', label: 'У рабочего', title: 'В работе у рабочего', hint: 'ещё не отправлены или возвращены', color: 'var(--warn-fg)', count: of('none', 'returned').length },
  { v: 'accepted', label: 'Принятые', title: 'Принятые проекты', hint: 'проверка пройдена', color: 'var(--ok-fg)', count: of('accepted').length },
])
const tabAll = computed(() => {
  if (tab.value === 'review') return of('review')
  if (tab.value === 'accepted') return of('accepted')
  // возвращённые выше тех, что ещё не отправляли
  return [...of('returned'), ...of('none')]
})
const tabProjects = computed(() => tabAll.value.filter(matches))
const emptyText = {
  review: 'Сейчас проверять нечего',
  worker: 'У рабочих нет проектов в работе',
  accepted: 'Принятых проектов пока нет',
}

const VISIBLE_LIMIT = 6
const expanded = ref(false)
const visibleProjects = computed(() => (expanded.value ? tabProjects.value : tabProjects.value.slice(0, VISIBLE_LIMIT)))
const hiddenCount = computed(() => Math.max(0, tabProjects.value.length - VISIBLE_LIMIT))
function setTab(v) { tab.value = v; expanded.value = false }

const lastComment = (p) => p.comments[p.comments.length - 1]

const modal = ref(false)
const currentId = ref(null)
const current = computed(() => projects.value.find(p => p.id === currentId.value) || null)
function open(p) { currentId.value = p.id; modal.value = true }
function onUpdate(fresh) {
  const i = projects.value.findIndex(p => p.id === fresh.id)
  if (i >= 0) projects.value[i] = fresh
}

async function load() {
  // свои проекты (если человек ещё и рабочий) здесь не показываем — их проверяют другие
  projects.value = (await api.get('/projects/')).data.filter(p => p.worker !== auth.user?.id)
  loaded.value = true
}
onMounted(load)
</script>

<style scoped>
.wbody { max-width: 1100px; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.stat { cursor: pointer; transition: transform .25s cubic-bezier(.16,1,.3,1), border-color .25s; }
.stat:hover { transform: translateY(-2px); }
.stat.on { border-color: var(--brand); }
.stat-val { font-size: 34px; font-weight: 800; letter-spacing: -.03em; margin: 4px 0; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; position: relative; }
.pcard { display: flex; flex-direction: column; gap: 12px; cursor: pointer; transition: transform .25s cubic-bezier(.16,1,.3,1), border-color .25s, box-shadow .25s; }
.pcard:hover { transform: translateY(-3px); border-color: var(--stroke-strong); box-shadow: var(--shadow); }
.p-name { margin: 0; font-size: 18px; font-weight: 700; }
.dates { display: flex; justify-content: space-between; }
.dates div { display: flex; flex-direction: column; gap: 3px; }
.last { padding: 12px; border-radius: 12px; background: var(--input-bg); }
.last-text { margin-top: 4px; font-size: 14px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; padding-top: 10px; border-top: 1px solid var(--stroke); margin-top: auto; }
.tab-count { opacity: .7; font-weight: 700; margin-left: 2px; }
.more-row { display: flex; justify-content: center; margin-top: 20px; }
.more-btn { border-radius: 999px; padding: 11px 22px; }
.more-btn .chev { transition: transform .35s cubic-bezier(.16,1,.3,1); }
.more-btn.open .chev { transform: rotate(180deg); }
@media (max-width: 700px) { .stats { grid-template-columns: 1fr; }  }
</style>
