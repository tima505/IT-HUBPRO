<template>
  <div class="bell-wrap">
    <button class="bell" :class="{ ring: unread > 0 }" title="Уведомления" @click="toggle">
      <Icon name="bell" :size="19" />
      <transition name="pop">
        <span v-if="unread > 0" class="dot">{{ unread }}</span>
      </transition>
    </button>

    <transition name="pop">
      <div v-if="open" class="bell-panel card" @click.stop>
        <div class="row between" style="margin-bottom: 10px">
          <b>Уведомления</b>
          <button v-if="notifications.length" class="btn ghost sm" @click="markAll">Прочитать все</button>
        </div>
        <div v-if="!notifications.length" class="muted small center" style="padding: 24px 0">
          Пока нет уведомлений
        </div>
        <transition-group name="list" tag="div" class="notif-list">
          <div v-for="n in notifications" :key="n.id" class="notif" :class="{ unread: !n.is_read }" @click="markRead(n)">
            <div class="n-ico"><Icon :name="icons[n.kind] || 'calendar'" :size="17" /></div>
            <div class="grow">
              <div class="n-title">{{ n.title }}</div>
              <div class="muted small">{{ n.message }}</div>
            </div>
          </div>
        </transition-group>
      </div>
    </transition>

    <div v-if="open" class="bell-catch" @click="open = false"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../api'
import Icon from './Icon.vue'

// 'tick' — раз в 30 секунд и после действий: родитель может обновить свои данные
const emit = defineEmits(['tick'])
const icons = { server: 'server', project: 'calendar', review: 'check-circle' }

const unread = ref(0)
const open = ref(false)
const notifications = ref([])
let timer = null

async function refresh() {
  try {
    const { data } = await api.get('/notifications/unread_count/')
    // пришло новое уведомление — даём странице повод перечитать данные
    if (data.count > unread.value) emit('tick')
    unread.value = data.count
  } catch (e) { /* ignore */ }
}

async function toggle() {
  open.value = !open.value
  if (open.value) notifications.value = (await api.get('/notifications/')).data
}
async function markRead(n) {
  if (n.is_read) return
  await api.post(`/notifications/${n.id}/mark_read/`)
  n.is_read = true
  refresh()
}
async function markAll() {
  await api.post('/notifications/mark_all_read/')
  notifications.value.forEach(n => (n.is_read = true))
  refresh()
}

defineExpose({ refresh })

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 30000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.bell-wrap { position: relative; }
.bell { position: relative; display: grid; place-items: center; width: 44px; height: 44px; border-radius: 12px; border: 1px solid var(--stroke-strong);
  background: var(--card-2); color: var(--text); cursor: pointer; transition: all .2s; }
.bell:hover { background: var(--hover); }
.bell.ring { animation: pulseRing 2.5s infinite; }
.dot { position: absolute; top: -6px; right: -6px; background: var(--c-red); color: #fff; font-size: 11px; font-weight: 700;
  min-width: 20px; height: 20px; border-radius: 999px; display: grid; place-items: center; padding: 0 5px; border: 2px solid var(--panel); }
.bell-panel { position: absolute; right: 0; top: 56px; width: 360px; max-width: calc(100vw - 32px); z-index: 40; max-height: 460px; overflow-y: auto; box-shadow: var(--shadow); }
.bell-catch { position: fixed; inset: 0; z-index: 30; }
.notif-list { display: flex; flex-direction: column; gap: 6px; }
.notif { display: flex; gap: 12px; padding: 12px; border-radius: 12px; cursor: pointer; transition: background .2s; border: 1px solid transparent; }
.notif:hover { background: var(--hover); }
.notif.unread { background: var(--info-bg); }
.n-ico { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 10px; background: var(--card-2); color: var(--brand); flex-shrink: 0; }
.n-title { font-weight: 600; font-size: 14px; }
</style>
