<template>
  <article class="tcard" :class="['prio-' + task.priority, { done: task.status === 'done' }]" @click="$emit('open', task)">
    <div class="t-top">
      <span v-if="task.project_name" class="t-project ellipsis"><Icon name="folder" :size="12" /> {{ task.project_name }}</span>
      <span class="t-prio" :title="'Приоритет: ' + task.priority_display">{{ prioLabel[task.priority] }}</span>
    </div>

    <h4 class="t-title">{{ task.title }}</h4>

    <div v-if="task.subtasks_total" class="t-sub">
      <Icon name="list-checks" :size="14" />
      <div class="progress grow" :class="{ ok: task.subtasks_done === task.subtasks_total }">
        <span :style="{ width: (task.subtasks_done / task.subtasks_total * 100) + '%' }"></span>
      </div>
      <span class="mono small">{{ task.subtasks_done }}/{{ task.subtasks_total }}</span>
    </div>

    <div class="t-foot">
      <span v-if="deadline" class="badge" :class="deadline.cls"><Icon :name="deadline.icon" :size="12" /> {{ deadline.text }}</span>
      <span v-else class="muted small">без срока</span>
      <div v-if="showAssignee" class="avatar xs" :title="task.assignee_name">{{ initials(task.assignee_name) }}</div>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { formatDate } from '../api'
import Icon from './Icon.vue'

const props = defineProps({
  task: { type: Object, required: true },
  showAssignee: { type: Boolean, default: false },
})
defineEmits(['open'])

const prioLabel = { high: 'Высокий', medium: 'Средний', low: 'Низкий' }

const deadline = computed(() => {
  const t = props.task
  if (!t.deadline) return null
  const date = formatDate(t.deadline).slice(0, 5)
  return {
    overdue: { cls: 'red', icon: 'alert', text: `Просрочено · ${date}` },
    today: { cls: 'amber', icon: 'clock', text: 'Сегодня' },
    soon: { cls: 'amber', icon: 'clock', text: date },
    ok: { cls: 'gray', icon: 'calendar', text: date },
    on_time: { cls: 'green', icon: 'check-circle', text: 'В срок' },
    late: { cls: 'red', icon: 'alert', text: 'С опозданием' },
  }[t.deadline_state] || { cls: 'gray', icon: 'calendar', text: date }
})

function initials(name = '') {
  return name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase()
}
</script>

<style scoped>
.tcard {
  position: relative; display: flex; flex-direction: column; gap: 10px; padding: 13px 14px 12px 16px;
  background: var(--card); border: 1px solid var(--stroke); border-radius: 14px; cursor: grab;
  transition: border-color .2s, box-shadow .2s, transform .2s; user-select: none;
}
.tcard::before {
  content: ''; position: absolute; left: 0; top: 12px; bottom: 12px; width: 3px; border-radius: 0 3px 3px 0;
  background: var(--prio);
}
.tcard:hover { border-color: var(--stroke-strong); box-shadow: var(--shadow); transform: translateY(-1px); }
.tcard.done .t-title { color: var(--muted); text-decoration: line-through; text-decoration-color: var(--muted-2); }
.prio-high { --prio: var(--c-red); }
.prio-medium { --prio: var(--c-amber); }
.prio-low { --prio: var(--c-sky); }
.t-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 18px; }
.t-project { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--muted); max-width: 70%; }
.t-prio { margin-left: auto; font-family: var(--font-mono); font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--prio); font-weight: 600; }
.t-title { margin: 0; font-size: 14.5px; font-weight: 600; line-height: 1.4; word-break: break-word; }
.t-sub { display: flex; align-items: center; gap: 8px; color: var(--muted); }
.t-foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
</style>
