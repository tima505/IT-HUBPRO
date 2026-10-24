<template>
  <Modal :model-value="modelValue" @update:model-value="close" wide
         :eyebrow="isNew ? 'Новая задача' : (task?.status_display || 'Задача')"
         :title="isNew ? 'Создать задачу' : 'Задача'">
    <form @submit.prevent="save" class="tm">
      <input v-model="form.title" class="input title-input" placeholder="Что нужно сделать?" maxlength="200" required />
      <textarea v-model="form.description" class="input" rows="3" placeholder="Описание, ссылки, детали…"></textarea>

      <div class="grid-2">
        <div class="field" v-if="auth.isAdmin">
          <label>Исполнитель</label>
          <select v-model="form.assignee" class="select input" required>
            <option :value="null" disabled>Выберите…</option>
            <option v-for="u in assignees" :key="u.id" :value="u.id">
              {{ u.full_name || u.username }}{{ u.roles?.includes('admin') ? ' (админ)' : '' }}
            </option>
          </select>
        </div>
        <div class="field">
          <label>Проект</label>
          <select v-model="form.project" class="select input">
            <option :value="null">Без проекта</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div class="field">
          <label>Дедлайн</label>
          <input v-model="form.deadline" type="date" class="input" />
        </div>
        <div class="field">
          <label>Статус</label>
          <select v-model="form.status" class="select input">
            <option v-for="c in columns" :key="c.key" :value="c.key">{{ c.title }}</option>
          </select>
        </div>
      </div>

      <div class="field">
        <label>Приоритет</label>
        <div class="segmented prio">
          <button v-for="p in priorities" :key="p.key" type="button" :class="['p-' + p.key, { active: form.priority === p.key }]"
                  @click="form.priority = p.key">{{ p.label }}</button>
        </div>
      </div>

      <!-- Подзадачи -->
      <section class="subs">
        <div class="row between">
          <div class="row gap-8"><Icon name="list-checks" :size="18" /> <b>Подзадачи</b></div>
          <span v-if="subtasks.length" class="muted small mono">{{ doneCount }}/{{ subtasks.length }}</span>
        </div>
        <div v-if="subtasks.length" class="progress" :class="{ ok: doneCount === subtasks.length }">
          <span :style="{ width: (doneCount / subtasks.length * 100) + '%' }"></span>
        </div>
        <transition-group name="list" tag="div" class="sub-list">
          <div v-for="(st, i) in subtasks" :key="st.id || st.tmp" class="sub-item" :class="{ done: st.is_done }">
            <label class="check">
              <input type="checkbox" :checked="st.is_done" @change="toggleSub(st)" />
              <span class="box"><Icon name="check" :size="14" :stroke-width="3" /></span>
            </label>
            <span class="grow sub-title">{{ st.title }}</span>
            <button type="button" class="btn ghost sm icon-btn" title="Удалить" @click="removeSub(st, i)"><Icon name="close" :size="14" /></button>
          </div>
        </transition-group>
        <div class="row gap-8">
          <input v-model="newSub" class="input" placeholder="Добавить подзадачу и нажать Enter"
                 maxlength="200" @keydown.enter.prevent="addSub" />
          <button type="button" class="btn icon-btn" :disabled="!newSub.trim()" @click="addSub"><Icon name="plus" :size="18" /></button>
        </div>
      </section>

      <div v-if="task && !isNew" class="meta muted small">
        Создал(а): {{ task.created_by_name || '—' }} · {{ formatDateTime(task.created_at) }}
        <template v-if="task.completed_at"> · выполнена {{ formatDateTime(task.completed_at) }}</template>
      </div>

      <div v-if="error" class="badge red">{{ error }}</div>

      <div class="actions">
        <button v-if="canDelete" type="button" class="btn danger" @click="remove" :disabled="busy">
          <Icon name="trash" :size="16" /> <span class="hide-xs">Удалить</span>
        </button>
        <div class="grow"></div>
        <button type="button" class="btn ghost" @click="close">Отмена</button>
        <button class="btn primary" :disabled="busy || !form.title.trim()">
          <span v-if="busy" class="spinner"></span>
          <template v-else><Icon name="check" :size="16" /> {{ isNew ? 'Создать' : 'Сохранить' }}</template>
        </button>
      </div>
    </form>
  </Modal>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import api, { errorMessage } from '../api'
import { useAuth } from '../stores/auth'
import Modal from './Modal.vue'
import Icon from './Icon.vue'

const props = defineProps({
  modelValue: Boolean,
  task: { type: Object, default: null },          // null — создание
  defaults: { type: Object, default: () => ({}) }, // статус/исполнитель для новой задачи
  columns: { type: Array, required: true },
  assignees: { type: Array, default: () => [] },
  projects: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'saved', 'deleted'])
const auth = useAuth()

const priorities = [
  { key: 'low', label: 'Низкий' },
  { key: 'medium', label: 'Средний' },
  { key: 'high', label: 'Высокий' },
]

const form = reactive({ title: '', description: '', assignee: null, project: null, deadline: '', status: 'todo', priority: 'medium' })
const subtasks = ref([])
const newSub = ref('')
const busy = ref(false)
const error = ref('')
let tmpId = 0

const isNew = computed(() => !props.task)
const doneCount = computed(() => subtasks.value.filter(s => s.is_done).length)
const canDelete = computed(() => props.task && (auth.isAdmin || props.task.created_by === auth.user?.id))

watch(() => props.modelValue, (open) => {
  if (!open) return
  const t = props.task
  Object.assign(form, {
    title: t?.title || '',
    description: t?.description || '',
    assignee: t?.assignee ?? props.defaults.assignee ?? (auth.isAdmin ? null : auth.user?.id),
    project: t?.project ?? props.defaults.project ?? null,
    deadline: t?.deadline || '',
    status: t?.status || props.defaults.status || 'todo',
    priority: t?.priority || 'medium',
  })
  subtasks.value = (t?.subtasks || []).map(s => ({ ...s }))
  newSub.value = ''
  error.value = ''
})

function close() { emit('update:modelValue', false) }

function payload() {
  const data = { ...form, deadline: form.deadline || null, title: form.title.trim() }
  if (!auth.isAdmin) delete data.assignee
  return data
}

async function save() {
  busy.value = true; error.value = ''
  try {
    let saved
    if (isNew.value) {
      saved = (await api.post('/tasks/', payload(), { silentError: true })).data
      // подзадачи, набранные до создания задачи
      for (const st of subtasks.value) {
        await api.post('/subtasks/', { task: saved.id, title: st.title, is_done: st.is_done })
      }
      if (subtasks.value.length) saved = (await api.get(`/tasks/${saved.id}/`)).data
    } else {
      saved = (await api.patch(`/tasks/${props.task.id}/`, payload(), { silentError: true })).data
    }
    emit('saved', saved)
    close()
  } catch (e) {
    error.value = errorMessage(e, 'Не удалось сохранить задачу')
  } finally { busy.value = false }
}

async function addSub() {
  const title = newSub.value.trim()
  if (!title) return
  newSub.value = ''
  if (isNew.value) {
    subtasks.value.push({ tmp: ++tmpId, title, is_done: false })
    return
  }
  const { data } = await api.post('/subtasks/', { task: props.task.id, title })
  subtasks.value.push(data)
  syncTask()
}

async function toggleSub(st) {
  st.is_done = !st.is_done
  if (!st.id) return
  try {
    await api.patch(`/subtasks/${st.id}/`, { is_done: st.is_done })
    syncTask()
  } catch { st.is_done = !st.is_done }
}

async function removeSub(st, i) {
  if (st.id) await api.delete(`/subtasks/${st.id}/`)
  subtasks.value.splice(i, 1)
  if (st.id) syncTask()
}

// подзадачи сохраняются сразу — обновляем карточку на доске
async function syncTask() {
  const { data } = await api.get(`/tasks/${props.task.id}/`)
  emit('saved', data, { keepOpen: true })
}

async function remove() {
  if (!confirm(`Удалить задачу «${props.task.title}»?`)) return
  busy.value = true
  try {
    await api.delete(`/tasks/${props.task.id}/`)
    emit('deleted', props.task)
    close()
  } finally { busy.value = false }
}

function formatDateTime(v) {
  if (!v) return ''
  return new Date(v).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.tm { display: flex; flex-direction: column; gap: 14px; }
.title-input { font-size: 18px; font-weight: 700; padding: 13px 14px; }
.segmented.prio { width: 100%; }
.segmented.prio button { flex: 1; }
.segmented.prio .p-high.active { color: var(--c-red); }
.segmented.prio .p-medium.active { color: var(--c-amber); }
.segmented.prio .p-low.active { color: var(--c-sky); }
.subs { display: flex; flex-direction: column; gap: 10px; padding: 14px; border-radius: 14px; background: var(--card-2); border: 1px solid var(--stroke); }
.sub-list { display: flex; flex-direction: column; gap: 4px; position: relative; }
.sub-item { display: flex; align-items: center; gap: 10px; padding: 6px 6px 6px 8px; border-radius: 10px; transition: background .2s; }
.sub-item:hover { background: var(--hover); }
.sub-item.done .sub-title { color: var(--muted); text-decoration: line-through; }
.sub-title { font-size: 14px; word-break: break-word; }
.meta { line-height: 1.5; }
.actions { display: flex; align-items: center; gap: 10px; padding-top: 6px; border-top: 1px solid var(--stroke); padding-top: 14px; }
@media (max-width: 480px) { .hide-xs { display: none; } }
</style>
