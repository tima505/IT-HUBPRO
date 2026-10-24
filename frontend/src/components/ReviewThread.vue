<template>
  <div class="thread">
    <div class="row between wrap gap-8 thread-head">
      <div class="row gap-8 wrap">
        <ReviewBadge :status="project.review_status" />
        <span class="muted small">
          Рабочий: <b class="strong">{{ project.worker_name || project.worker_username || '—' }}</b>
          <template v-if="project.reviewer_name">· Проверил: <b class="strong">{{ project.reviewer_name }}</b></template>
        </span>
      </div>
    </div>

    <div ref="listEl" class="msgs">
      <div v-if="!project.comments?.length" class="muted small center" style="padding: 22px 0">
        Переписки пока нет
      </div>
      <div v-for="c in project.comments" :key="c.id" class="msg" :class="[c.kind, { mine: c.author === auth.user?.id }]">
        <div class="row between gap-8 wrap">
          <div class="row gap-8 wrap">
            <b>{{ c.author_name }}</b>
            <span class="muted small">{{ roleLabel[c.author_role] || '' }}</span>
            <span v-if="c.kind !== 'comment'" class="badge" :class="kindCls[c.kind]">{{ c.kind_display }}</span>
          </div>
          <span class="muted small">{{ formatDateTime(c.created_at) }}</span>
        </div>
        <div v-if="c.text" class="msg-text">{{ c.text }}</div>
      </div>
    </div>

    <div class="hint muted small">{{ hint }}</div>

    <textarea v-model="text" class="input" rows="3" :placeholder="placeholder" @keydown.ctrl.enter="send('comment')"></textarea>

    <transition name="pop"><div v-if="error" class="badge red">{{ error }}</div></transition>

    <div class="row gap-8 wrap actions">
      <button v-if="canSubmit" class="btn primary" :disabled="busy || !text.trim()" @click="send('submit')">
        <Icon name="send" :size="15" /> Отправить на проверку
      </button>
      <template v-if="canReview">
        <button class="btn green" :disabled="busy" @click="send('accept')"><Icon name="check" :size="15" /> Принять проект</button>
        <button class="btn danger" :disabled="busy || !text.trim()" title="Опишите недостатки в поле выше" @click="send('return')">
          <Icon name="undo" :size="15" /> Вернуть на доработку
        </button>
      </template>
      <button class="btn" :class="{ ghost: canSubmit || canReview }" :disabled="busy || !text.trim()" @click="send('comment')">
        <Icon name="message" :size="15" /> Комментарий
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import api from '../api'
import { useAuth } from '../stores/auth'
import Icon from './Icon.vue'
import ReviewBadge from './ReviewBadge.vue'

const props = defineProps({ project: { type: Object, required: true } })
// 'update' отдаёт свежий проект — родитель подменяет его у себя
const emit = defineEmits(['update'])
const auth = useAuth()

const text = ref('')
const busy = ref(false)
const error = ref('')
const listEl = ref(null)

const roleLabel = { admin: 'админ', worker: 'рабочий', tester: 'тестировщик' }
const kindCls = { submit: 'blue', accept: 'green', return: 'red' }

const p = computed(() => props.project)
// роли совмещаются: «рабочий» — это автор именно этого проекта, свой проект проверять нельзя
const isWorker = computed(() => p.value.worker === auth.user?.id)
const isTester = computed(() => auth.hasRole('tester') && !isWorker.value)
const canSubmit = computed(() =>
  isWorker.value && p.value.status === 'active' && ['none', 'returned'].includes(p.value.review_status))
const canReview = computed(() => (isTester.value || auth.isAdmin) && p.value.review_status === 'review')

const hint = computed(() => {
  const s = p.value.review_status
  if (canSubmit.value) return s === 'returned'
    ? 'Проект вернули. Исправьте замечания, напишите, что исправлено, и отправьте снова.'
    : 'Напишите, что сделано и что проверить, затем отправьте — проект увидят все тестировщики.'
  if (canReview.value) return 'Примите проект или верните его — при возврате обязательно опишите недостатки.'
  if (s === 'review') return 'Проект на проверке — его примет или вернёт первый свободный тестировщик.'
  if (s === 'accepted') return `Проект принят${p.value.reviewer_name ? ` (${p.value.reviewer_name})` : ''}.`
  if (s === 'returned') return 'Проект возвращён рабочему на доработку.'
  return 'Рабочий ещё не отправлял проект на проверку.'
})
const placeholder = computed(() => {
  if (canSubmit.value) return 'Что добавлено / исправлено, что проверить…'
  if (canReview.value) return 'Замечания и недостатки (обязательно при возврате)…'
  return 'Ваш комментарий…'
})

function formatDateTime(iso) {
  const d = new Date(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function scrollDown() {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
}

async function send(action) {
  if (busy.value) return
  const body = { text: text.value.trim() }
  if (action !== 'accept' && !body.text) return
  let url = `/projects/${p.value.id}/comment/`
  if (action === 'submit') url = `/projects/${p.value.id}/submit/`
  if (action === 'accept' || action === 'return') {
    url = `/projects/${p.value.id}/review/`
    body.decision = action
  }
  busy.value = true; error.value = ''
  try {
    const { data } = await api.post(url, body)
    text.value = ''
    emit('update', data)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Не удалось отправить'
  } finally { busy.value = false }
}

watch(() => props.project.comments?.length, scrollDown)
onMounted(scrollDown)
</script>

<style scoped>
.thread { display: flex; flex-direction: column; gap: 12px; }
.strong { color: var(--text); }
.msgs { display: flex; flex-direction: column; gap: 8px; max-height: 340px; overflow-y: auto; padding-right: 4px; }
.msg { padding: 12px 14px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); border-left: 3px solid var(--stroke-strong); font-size: 14px; }
.msg.mine { background: var(--card-2); }
.msg.submit { border-left-color: var(--c-blue); }
.msg.accept { border-left-color: var(--c-emerald); }
.msg.return { border-left-color: var(--c-red); }
.msg-text { margin-top: 6px; white-space: pre-wrap; word-break: break-word; line-height: 1.5; }
.hint { padding: 10px 12px; border-radius: 10px; background: var(--info-bg); color: var(--info-fg); }
textarea.input { resize: vertical; min-height: 78px; font-family: inherit; }
.actions { justify-content: flex-end; }
</style>
