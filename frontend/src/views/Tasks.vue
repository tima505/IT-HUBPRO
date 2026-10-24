<template>
  <div class="tasks-page">
    <!-- Панель фильтров -->
    <div class="toolbar">
      <div class="search">
        <Icon name="search" :size="17" />
        <input v-model="filters.q" class="input" placeholder="Поиск задач…" />
      </div>
      <select v-if="auth.isAdmin" v-model="filters.assignee" class="select input fsel">
        <option value="">Вся команда</option>
        <option value="me">Мои задачи</option>
        <option v-for="u in assignees" :key="u.id" :value="String(u.id)">{{ u.full_name || u.username }}</option>
      </select>
      <select v-model="filters.project" class="select input fsel">
        <option value="">Все проекты</option>
        <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
      </select>
      <button class="btn primary new-btn" @click="openNew('todo')" aria-label="Новая задача"><Icon name="plus" :size="18" /> <span class="new-txt">Задача</span></button>
    </div>

    <!-- Итоги -->
    <div class="summary">
      <div class="sum-item"><b class="mono">{{ total }}</b><span class="muted small">всего</span></div>
      <div class="sum-item"><b class="mono">{{ board.in_progress.length + board.review.length }}</b><span class="muted small">в работе</span></div>
      <div class="sum-item ok"><b class="mono">{{ board.done.length }}</b><span class="muted small">готово</span></div>
      <div class="sum-item bad" v-if="overdue"><b class="mono">{{ overdue }}</b><span class="muted small">просрочено</span></div>
    </div>

    <!-- Переключатель колонок (мобильные) -->
    <div class="col-tabs">
      <button v-for="c in COLUMNS" :key="c.key" :class="{ active: activeCol === c.key }" @click="scrollToCol(c.key)">
        <span class="cdot" :style="{ background: c.color }"></span>{{ c.short }} <span class="mono">{{ board[c.key].length }}</span>
      </button>
    </div>

    <!-- Доска -->
    <div class="board" ref="boardEl" @scroll.passive="onBoardScroll">
      <section v-for="c in COLUMNS" :key="c.key" class="column" :data-col="c.key">
        <header class="col-head">
          <div class="row gap-8">
            <span class="cdot" :style="{ background: c.color }"></span>
            <b>{{ c.title }}</b>
            <span class="count mono">{{ board[c.key].length }}</span>
          </div>
          <button class="btn ghost sm icon-btn" :title="'Добавить в «' + c.title + '»'" @click="openNew(c.key)"><Icon name="plus" :size="16" /></button>
        </header>

        <draggable
          v-model="board[c.key]"
          item-key="id"
          group="tasks"
          class="col-body"
          ghost-class="drag-ghost"
          chosen-class="drag-chosen"
          :animation="180"
          :delay="180"
          :delay-on-touch-only="true"
          :touch-start-threshold="6"
          @change="(e) => onChange(c.key, e)"
        >
          <template #item="{ element }">
            <TaskCard :task="element" :show-assignee="auth.isAdmin" @open="openTask" />
          </template>
          <template #footer>
            <div v-if="!board[c.key].length" class="col-empty muted small">
              {{ loading ? 'Загрузка…' : 'Перетащите сюда задачу' }}
            </div>
          </template>
        </draggable>
      </section>
    </div>

    <TaskModal
      v-model="modal"
      :task="current"
      :defaults="defaults"
      :columns="COLUMNS"
      :assignees="assignees"
      :projects="projects"
      @saved="onSaved"
      @deleted="onDeleted"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import draggable from 'vuedraggable'
import api from '../api'
import { useAuth } from '../stores/auth'
import Icon from '../components/Icon.vue'
import TaskCard from '../components/TaskCard.vue'
import TaskModal from '../components/TaskModal.vue'

const auth = useAuth()

const COLUMNS = [
  { key: 'todo', title: 'К выполнению', short: 'Сделать', color: '#94a3b8' },
  { key: 'in_progress', title: 'В работе', short: 'В работе', color: '#6366f1' },
  { key: 'review', title: 'На проверке', short: 'Проверка', color: '#f59e0b' },
  { key: 'done', title: 'Готово', short: 'Готово', color: '#10b981' },
]

const FILTERS_KEY = 'tasks.filters'
function loadFilters() {
  try { return JSON.parse(localStorage.getItem(FILTERS_KEY)) || {} } catch { return {} }
}
const filters = reactive({ q: '', assignee: '', project: '', ...loadFilters() })
watch(filters, (v) => {
  try { localStorage.setItem(FILTERS_KEY, JSON.stringify({ assignee: v.assignee, project: v.project })) } catch { /* приватный режим */ }
})

const board = reactive(Object.fromEntries(COLUMNS.map(c => [c.key, []])))
const assignees = ref([])
const projects = ref([])
const loading = ref(true)
const modal = ref(false)
const current = ref(null)
const defaults = ref({})

const total = computed(() => COLUMNS.reduce((n, c) => n + board[c.key].length, 0))
const overdue = computed(() => COLUMNS.reduce((n, c) => n + board[c.key].filter(t => t.deadline_state === 'overdue').length, 0))

async function load() {
  const params = {}
  if (filters.assignee) params.assignee = filters.assignee
  if (filters.project) params.project = filters.project
  if (filters.q.trim()) params.q = filters.q.trim()
  const { data } = await api.get('/tasks/', { params })
  for (const c of COLUMNS) board[c.key] = data.filter(t => t.status === c.key)
  loading.value = false
}

let searchTimer = null
watch(() => [filters.assignee, filters.project], load)
watch(() => filters.q, () => { clearTimeout(searchTimer); searchTimer = setTimeout(load, 300) })

// перетаскивание: сохраняем новый порядок колонки, в которую попала карточка
async function onChange(colKey, e) {
  if (!e.added && !e.moved) return
  const ids = board[colKey].map(t => t.id)
  if (e.added) {
    const t = e.added.element
    t.status = colKey
    t.status_display = COLUMNS.find(c => c.key === colKey).title
  }
  try {
    const { data } = await api.post('/tasks/reorder/', { status: colKey, ids })
    const fresh = Object.fromEntries(data.map(t => [t.id, t]))
    board[colKey] = board[colKey].map(t => fresh[t.id] || t)
  } catch {
    await load()  // вернуть доску к состоянию сервера
  }
}

function openNew(status) {
  current.value = null
  defaults.value = {
    status,
    assignee: auth.isAdmin && /^\d+$/.test(filters.assignee) ? Number(filters.assignee) : undefined,
    project: filters.project ? Number(filters.project) : undefined,
  }
  modal.value = true
}
function openTask(task) {
  current.value = task
  modal.value = true
}

function removeFromBoard(id) {
  for (const c of COLUMNS) board[c.key] = board[c.key].filter(t => t.id !== id)
}
function onSaved(task, opts = {}) {
  const col = board[task.status]
  const idx = col.findIndex(t => t.id === task.id)
  if (idx >= 0) {
    col.splice(idx, 1, task)
  } else {
    removeFromBoard(task.id)
    col.push(task)
  }
  if (opts.keepOpen) current.value = task
}
function onDeleted(task) { removeFromBoard(task.id) }

// мобильные: колонки листаются свайпом, вкладки сверху показывают текущую
const boardEl = ref(null)
const activeCol = ref('todo')
function scrollToCol(key) {
  const el = boardEl.value?.querySelector(`[data-col="${key}"]`)
  if (el) boardEl.value.scrollTo({ left: el.offsetLeft - boardEl.value.offsetLeft, behavior: 'smooth' })
}
function onBoardScroll() {
  const el = boardEl.value
  if (!el) return
  const cols = [...el.querySelectorAll('.column')]
  const i = cols.findIndex(c => c.offsetLeft - el.offsetLeft + c.offsetWidth / 2 > el.scrollLeft)
  activeCol.value = COLUMNS[Math.max(0, i)].key
}

onMounted(async () => {
  const [a, p] = await Promise.all([api.get('/tasks/assignees/'), api.get('/projects/')])
  assignees.value = a.data
  projects.value = p.data
  // фильтр из прошлой сессии мог указывать на удалённого человека/проект
  if (filters.assignee && !['me'].includes(filters.assignee) && !a.data.some(u => String(u.id) === filters.assignee)) filters.assignee = ''
  if (filters.project && !p.data.some(x => String(x.id) === filters.project)) filters.project = ''
  await load()
})
</script>

<style scoped>
.tasks-page { display: flex; flex-direction: column; gap: 16px; }
.toolbar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.search { position: relative; flex: 1 1 240px; }
.search .icon { position: absolute; left: 13px; top: 50%; transform: translateY(-50%); color: var(--muted-2); }
.search .input { padding-left: 38px; }
.fsel { width: auto; flex: 0 1 200px; }
.new-btn { flex-shrink: 0; }

.summary { display: flex; gap: 10px; flex-wrap: wrap; }
.sum-item { display: flex; align-items: baseline; gap: 6px; padding: 8px 14px; border-radius: 12px; background: var(--card-2); border: 1px solid var(--stroke); }
.sum-item b { font-size: 17px; }
.sum-item.ok b { color: var(--ok-fg); }
.sum-item.bad b { color: var(--bad-fg); }

.col-tabs { display: none; }

.board {
  display: grid; grid-template-columns: repeat(4, minmax(260px, 1fr)); gap: 14px; align-items: start;
  overflow-x: auto; padding-bottom: 6px;
}
.column {
  display: flex; flex-direction: column; min-height: 200px; max-height: calc(100vh - 250px);
  background: var(--card-2); border: 1px solid var(--stroke); border-radius: 18px;
}
.col-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 12px 10px 16px; }
.cdot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; display: inline-block; }
.count { font-size: 12px; color: var(--muted); background: var(--neutral-bg); border-radius: 99px; padding: 1px 8px; }
.col-body { flex: 1; display: flex; flex-direction: column; gap: 10px; padding: 2px 10px 12px; overflow-y: auto; min-height: 80px; }
.col-empty { padding: 22px 10px; text-align: center; border: 1.5px dashed var(--stroke-strong); border-radius: 12px; }
:deep(.drag-ghost) { opacity: .35; border: 1.5px dashed var(--brand) !important; }
:deep(.drag-chosen) { box-shadow: var(--shadow); transform: rotate(1.5deg); cursor: grabbing; }

@media (max-width: 1200px) {
  .board { grid-template-columns: repeat(4, 280px); }
}
@media (max-width: 900px) {
  .tasks-page { gap: 12px; }
  .toolbar { gap: 8px; }
  .search { flex: 1 1 calc(100% - 52px); order: 0; }
  .new-btn { order: 1; width: 44px; padding: 0; }
  .new-txt { display: none; }
  .fsel { order: 2; flex: 1 1 calc(50% - 4px); min-width: 0; }
  .summary { display: none; }
  .col-tabs {
    display: flex; gap: 6px; overflow-x: auto; margin: 0 -16px; padding: 0 16px; scrollbar-width: none;
  }
  .col-tabs::-webkit-scrollbar { display: none; }
  .col-tabs button {
    display: inline-flex; align-items: center; gap: 7px; flex-shrink: 0; padding: 8px 13px; border-radius: 99px;
    border: 1px solid var(--stroke); background: var(--card-2); color: var(--muted); font: 600 13px var(--font); cursor: pointer;
  }
  .col-tabs button.active { color: var(--text); border-color: var(--brand); background: var(--info-bg); }
  .board {
    grid-template-columns: repeat(4, calc(100vw - 48px)); gap: 12px; margin: 0 -16px; padding: 0 16px 6px;
    scroll-snap-type: x mandatory; scroll-padding: 0 16px; scrollbar-width: none;
  }
  .board::-webkit-scrollbar { display: none; }
  .column { scroll-snap-align: start; max-height: none; }
  .col-body { overflow: visible; }
}
</style>
