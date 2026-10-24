<template>
  <div class="shell">
    <!-- Боковое меню (десктоп) -->
    <aside class="sidebar">
      <div class="brand">
        <div class="logo"><Icon name="code" :size="22" :stroke-width="2.2" /></div>
        <div class="brand-txt">
          <div class="brand-name">IT Hub<span class="grad-text">Pro</span></div>
          <div class="muted small">{{ auth.isAdmin ? 'панель управления' : 'рабочее пространство' }}</div>
        </div>
      </div>

      <nav class="nav">
        <template v-for="group in navGroups" :key="group.title">
          <div class="nav-group">{{ group.title }}</div>
          <router-link v-for="item in group.items" :key="item.to" :to="item.to" class="nav-item">
            <span class="nav-ico"><Icon :name="item.icon" :size="19" /></span>
            <span>{{ item.label }}</span>
            <span v-if="badgeFor(item)" class="nav-count">{{ badgeFor(item) }}</span>
          </router-link>
        </template>
      </nav>

      <div class="side-foot">
        <button v-if="canInstall" class="install-card" @click="installApp">
          <Icon name="smartphone" :size="18" />
          <div class="grow">
            <b>Установить приложение</b>
            <div class="muted small">на телефон или компьютер</div>
          </div>
        </button>
        <div class="user-chip">
          <div class="avatar">{{ initials }}</div>
          <div class="grow">
            <div class="uname ellipsis">{{ auth.user?.full_name || auth.user?.username }}</div>
            <div class="muted small ellipsis">{{ auth.user?.roles_display }}</div>
          </div>
          <button class="btn ghost sm icon-btn" title="Мой профиль" @click="profileOpen = true"><Icon name="settings" :size="16" /></button>
          <button class="btn ghost sm icon-btn" title="Выйти" @click="logout"><Icon name="logout" :size="16" /></button>
        </div>
      </div>
    </aside>

    <!-- Контент -->
    <main class="main">
      <header class="topbar">
        <div class="grow">
          <div class="eyebrow">{{ page.eyebrow }}</div>
          <div class="page-title ellipsis">{{ page.title }}</div>
        </div>

        <div class="row gap-8">
          <button class="btn ghost icon-btn hide-mobile" @click="toggleTheme" :title="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'">
            <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="19" />
          </button>

          <div class="bell-wrap">
            <button class="bell" :class="{ ring: unread > 0 }" @click="toggleBell" aria-label="Уведомления">
              <Icon name="bell" :size="19" />
              <transition name="pop">
                <span v-if="unread > 0" class="dot">{{ unread }}</span>
              </transition>
            </button>

            <transition name="pop">
              <div v-if="bellOpen" class="bell-panel card" @click.stop>
                <div class="row between" style="margin-bottom: 10px">
                  <b>Уведомления</b>
                  <button v-if="notifications.length" class="btn ghost sm" @click="markAll">Прочитать все</button>
                </div>
                <div v-if="!notifications.length" class="empty small">
                  <div class="empty-ico"><Icon name="bell" :size="22" /></div>
                  Пока нет уведомлений
                </div>
                <transition-group name="list" tag="div" class="notif-list">
                  <div v-for="n in notifications" :key="n.id" class="notif" :class="{ unread: !n.is_read }" @click="markRead(n)">
                    <div class="n-ico" :class="n.kind"><Icon :name="notifIcon[n.kind] || 'info'" :size="17" /></div>
                    <div class="grow">
                      <div class="n-title">{{ n.title }}</div>
                      <div class="muted small">{{ n.message }}</div>
                    </div>
                  </div>
                </transition-group>
              </div>
            </transition>
          </div>
        </div>
      </header>

      <div class="content">
        <router-view v-slot="{ Component }">
          <transition name="slide" mode="out-in" appear>
            <component :is="Component" @changed="refreshCounts" />
          </transition>
        </router-view>
      </div>
    </main>

    <!-- Нижняя панель (мобильные) -->
    <nav class="tabbar">
      <router-link v-for="item in tabItems" :key="item.to" :to="item.to" class="tab">
        <span class="tab-ico">
          <Icon :name="item.icon" :size="22" />
          <span v-if="badgeFor(item)" class="tab-dot">{{ badgeFor(item) }}</span>
        </span>
        <span class="tab-label">{{ item.short || item.label }}</span>
      </router-link>
      <button class="tab" :class="{ active: moreOpen || inMore }" @click="moreOpen = true">
        <span class="tab-ico"><Icon name="menu" :size="22" /></span>
        <span class="tab-label">Ещё</span>
      </button>
    </nav>

    <!-- Шторка «Ещё» -->
    <transition name="fade">
      <div v-if="moreOpen" class="sheet-backdrop" @click="moreOpen = false">
        <transition name="sheet" appear>
          <div class="sheet" @click.stop>
            <div class="sheet-handle"></div>
            <div class="user-chip">
              <div class="avatar">{{ initials }}</div>
              <div class="grow">
                <div class="uname ellipsis">{{ auth.user?.full_name || auth.user?.username }}</div>
                <div class="muted small ellipsis">{{ auth.user?.roles_display }}</div>
              </div>
              <button class="btn sm" @click="moreOpen = false; profileOpen = true"><Icon name="settings" :size="15" /> Профиль</button>
            </div>
            <div class="sheet-grid">
              <router-link v-for="item in moreItems" :key="item.to" :to="item.to" class="sheet-item" @click="moreOpen = false">
                <span class="sheet-ico"><Icon :name="item.icon" :size="20" /></span>
                <span>{{ item.label }}</span>
              </router-link>
            </div>
            <div class="sheet-actions">
              <button class="btn block" @click="toggleTheme">
                <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
                {{ theme === 'dark' ? 'Светлая тема' : 'Тёмная тема' }}
              </button>
              <button v-if="canInstall" class="btn primary block" @click="installApp">
                <Icon name="smartphone" :size="18" /> Установить приложение
              </button>
              <button class="btn danger block" @click="logout"><Icon name="logout" :size="18" /> Выйти</button>
            </div>
          </div>
        </transition>
      </div>
    </transition>

    <!-- Подсказка установки для iPhone -->
    <Modal v-model="iosHint" eyebrow="Приложение" title="Установка на iPhone">
      <ol class="ios-steps">
        <li>Нажмите <b>«Поделиться»</b> <Icon name="share" :size="16" /> внизу экрана Safari.</li>
        <li>Выберите <b>«На экран „Домой“»</b>.</li>
        <li>Нажмите <b>«Добавить»</b> — иконка IT HubPro появится на рабочем столе.</li>
      </ol>
      <button class="btn primary block mt-16" @click="iosHint = false">Понятно</button>
    </Modal>

    <ProfileModal v-model="profileOpen" />

    <div v-if="bellOpen" class="bell-catch" @click="bellOpen = false"></div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api'
import { useAuth } from '../stores/auth'
import { theme, toggleTheme } from '../theme'
import { canInstall, installApp, iosHint } from '../pwa'
import Icon from '../components/Icon.vue'
import Modal from '../components/Modal.vue'
import ProfileModal from '../components/ProfileModal.vue'

const auth = useAuth()
const router = useRouter()
const route = useRoute()

// пункты меню: у каждого — роли, которым он виден (пусто — всем); роли совмещаются
const NAV = [
  { title: 'Работа', items: [
    { to: '/dashboard', label: 'Дашборд', short: 'Главная', icon: 'dashboard', roles: ['admin'] },
    { to: '/tasks', label: 'Задачи', icon: 'kanban', badge: 'tasks' },
    { to: '/me', label: 'Мои проекты', short: 'Проекты', icon: 'user', roles: ['worker'] },
    { to: '/tester', label: 'Проверка', icon: 'shield', roles: ['tester'], badge: 'review' },
    { to: '/analytics', label: 'Аналитика', icon: 'chart' },
  ] },
  { title: 'Управление', items: [
    { to: '/projects', label: 'Проекты', icon: 'folder', roles: ['admin'] },
    { to: '/debts', label: 'Долги', icon: 'wallet', roles: ['admin'] },
    { to: '/users', label: 'Пользователи', icon: 'users', roles: ['admin'] },
    { to: '/finance', label: 'Финансы', icon: 'bank', roles: ['admin'] },
    { to: '/servers', label: 'Серверы', icon: 'server', roles: ['admin'] },
    { to: '/renewals', label: 'Продления', icon: 'renew', roles: ['admin'], badge: 'due' },
    { to: '/history', label: 'История', icon: 'history', roles: ['admin'] },
    { to: '/settings', label: 'Настройки', icon: 'settings', roles: ['admin'] },
  ] },
]
// нижняя панель на телефоне: 4 главных раздела, остальное — в «Ещё»
const TAB_ORDER = ['/dashboard', '/tasks', '/projects', '/me', '/tester', '/analytics']
const visible = (item) => !item.roles || item.roles.some(r => auth.hasRole(r))
const navGroups = computed(() => NAV
  .map(g => ({ ...g, items: g.items.filter(visible) }))
  .filter(g => g.items.length))
const allItems = computed(() => navGroups.value.flatMap(g => g.items))
const tabItems = computed(() => TAB_ORDER
  .map(to => allItems.value.find(i => i.to === to)).filter(Boolean).slice(0, 4))
const moreItems = computed(() => allItems.value.filter(i => !tabItems.value.includes(i)))
const inMore = computed(() => moreItems.value.some(i => route.path.startsWith(i.to)))

const titles = {
  '/dashboard': ['Обзор', 'Дашборд'],
  '/tasks': ['Канбан', 'Задачи'],
  '/analytics': ['Отчёт за месяц', 'Аналитика'],
  '/projects': ['Управление', 'Проекты'],
  '/debts': ['Кто сколько должен', 'Долги'],
  '/users': ['Команда', 'Пользователи'],
  '/history': ['Журнал', 'История'],
  '/tester': ['Кабинет тестировщика', 'Проверка проектов'],
  '/finance': ['Деньги', 'Финансы'],
  '/servers': ['Инфраструктура', 'Серверы'],
  '/renewals': ['Оплаты', 'Продление проектов'],
  '/settings': ['Система', 'Настройки'],
  '/me': ['Кабинет', 'Мои проекты'],
}
const page = computed(() => {
  const key = Object.keys(titles).find(k => route.path === k || route.path.startsWith(k + '/'))
  const [eyebrow, title] = titles[key] || ['Раздел', 'IT HubPro']
  if (key === '/projects' && route.path !== '/projects') {
    const t = route.path === '/projects/new' ? 'Новый проект'
      : route.path.endsWith('/edit') ? 'Редактирование проекта' : 'Карточка проекта'
    return { eyebrow, title: t }
  }
  return { eyebrow, title }
})

const initials = computed(() => {
  const n = auth.user?.full_name || auth.user?.username || '?'
  return n.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase()
})

const notifIcon = { server: 'server', project: 'calendar', task: 'kanban', review: 'shield' }
const unread = ref(0)
const counts = ref({ due: 0, tasks: 0, review: 0 })
const bellOpen = ref(false)
const moreOpen = ref(false)
const profileOpen = ref(false)
const notifications = ref([])
let timer = null

function badgeFor(item) {
  return item.badge ? counts.value[item.badge] || 0 : 0
}

async function refreshCounts() {
  try {
    const { data } = await api.get('/notifications/unread_count/')
    unread.value = data.count
    const tasks = await api.get('/tasks/', { params: { assignee: 'me' } })
    // на значке — горящие задачи: просрочены или дедлайн сегодня
    counts.value.tasks = tasks.data.filter(t => ['overdue', 'today'].includes(t.deadline_state)).length
    if (auth.isAdmin) {
      const due = await api.get('/projects/due_monthly/')
      counts.value.due = due.data.filter(p => p.days_left <= 3).length
    }
    if (auth.isTester) {
      // проекты, ждущие проверки (свои проекты тестировщик не проверяет)
      const projects = await api.get('/projects/')
      counts.value.review = projects.data.filter(p => p.review_status === 'review' && p.worker !== auth.user?.id).length
    }
  } catch (e) { /* ignore */ }
}

async function toggleBell() {
  bellOpen.value = !bellOpen.value
  if (bellOpen.value) {
    const { data } = await api.get('/notifications/')
    notifications.value = data
  }
}
async function markRead(n) {
  if (n.is_read) return
  await api.post(`/notifications/${n.id}/mark_read/`)
  n.is_read = true
  refreshCounts()
}
async function markAll() {
  await api.post('/notifications/mark_all_read/')
  notifications.value.forEach(n => (n.is_read = true))
  refreshCounts()
}

function logout() {
  moreOpen.value = false
  auth.logout()
  router.push('/login')
}

watch(() => route.fullPath, () => { bellOpen.value = false })

onMounted(() => {
  refreshCounts()
  timer = setInterval(refreshCounts, 30000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.shell { display: grid; grid-template-columns: 264px 1fr; min-height: 100vh; }
.sidebar {
  position: sticky; top: 0; height: 100vh; padding: 22px 16px;
  display: flex; flex-direction: column; gap: 8px; overflow-y: auto;
  background: var(--panel); border-right: 1px solid var(--stroke); backdrop-filter: blur(18px);
}
.brand { display: flex; align-items: center; gap: 12px; padding: 6px 8px 14px; }
.logo { width: 44px; height: 44px; border-radius: 13px; display: grid; place-items: center; color: #fff;
  background: var(--grad-brand); box-shadow: var(--brand-glow); flex-shrink: 0; }
.brand-name { font-weight: 800; letter-spacing: -.02em; font-size: 17px; }
.nav { display: flex; flex-direction: column; gap: 3px; }
.nav-group { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted-2); padding: 14px 14px 6px; }
.nav-item {
  display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-radius: 12px;
  color: var(--muted); font-weight: 600; font-size: 14px; transition: all .2s; position: relative;
}
.nav-item:hover { background: var(--hover); color: var(--text); }
.nav-item.router-link-active { background: var(--info-bg); color: var(--text); }
.nav-item.router-link-active::before {
  content: ''; position: absolute; left: -16px; top: 9px; bottom: 9px; width: 3px; border-radius: 0 3px 3px 0;
  background: var(--grad-tech);
}
.nav-item.router-link-active .nav-ico { color: var(--brand); }
[data-theme='dark'] .nav-item.router-link-active .nav-ico { color: var(--info-fg); }
.nav-ico { display: grid; place-items: center; width: 22px; }
.nav-count { margin-left: auto; background: var(--c-red); color: #fff; font-size: 11px; font-weight: 700;
  min-width: 20px; height: 20px; border-radius: 999px; display: grid; place-items: center; padding: 0 6px; }
.side-foot { margin-top: auto; display: flex; flex-direction: column; gap: 10px; padding-top: 14px; }
.install-card {
  display: flex; align-items: center; gap: 12px; text-align: left; padding: 12px; border-radius: 14px; cursor: pointer;
  border: 1px dashed color-mix(in srgb, var(--brand) 55%, transparent); background: var(--info-bg); color: var(--text);
  font-family: inherit; font-size: 13px; transition: transform .2s;
}
.install-card:hover { transform: translateY(-1px); }
.user-chip { display: flex; align-items: center; gap: 10px; padding: 10px; border-radius: 14px; background: var(--card-2); border: 1px solid var(--stroke); }
.uname { font-weight: 600; font-size: 14px; }

.main { display: flex; flex-direction: column; min-width: 0; }
.topbar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 18px 32px;
  border-bottom: 1px solid var(--stroke); position: sticky; top: 0; z-index: 30;
  background: var(--panel); backdrop-filter: blur(18px);
}
.page-title { font-size: 22px; font-weight: 800; letter-spacing: -.025em; margin-top: 3px; }
.content { padding: 28px 32px 48px; }

.bell-wrap { position: relative; }
.bell { position: relative; display: grid; place-items: center; width: 42px; height: 42px; border-radius: 12px; border: 1px solid var(--stroke-strong);
  background: var(--card-2); color: var(--text); cursor: pointer; transition: all .2s; }
.bell:hover { background: var(--hover); }
.bell.ring { animation: pulseRing 2.5s infinite; }
.dot { position: absolute; top: -6px; right: -6px; background: var(--c-red); color: #fff; font-size: 11px; font-weight: 700;
  min-width: 20px; height: 20px; border-radius: 999px; display: grid; place-items: center; padding: 0 5px; border: 2px solid var(--panel-solid); }
.bell-panel { position: absolute; right: 0; top: 54px; width: 380px; z-index: 40; max-height: 480px; overflow-y: auto; box-shadow: var(--shadow); background: var(--panel-solid); }
.bell-catch { position: fixed; inset: 0; z-index: 25; }
.notif-list { display: flex; flex-direction: column; gap: 6px; }
.notif { display: flex; gap: 12px; padding: 12px; border-radius: 12px; cursor: pointer; transition: background .2s; }
.notif:hover { background: var(--hover); }
.notif.unread { background: var(--info-bg); }
.n-ico { display: grid; place-items: center; width: 36px; height: 36px; border-radius: 10px; background: var(--card-2); color: var(--brand); flex-shrink: 0; }
.n-ico.task { color: var(--c-emerald); }
.n-ico.server { color: var(--c-sky); }
.n-title { font-weight: 600; font-size: 14px; }

.tabbar, .sheet-backdrop { display: none; }
.ios-steps { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 10px; line-height: 1.5; }

/* ---------- Мобильные ---------- */
@media (max-width: 900px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar, .hide-mobile { display: none; }
  .topbar { padding: calc(10px + var(--safe-top)) 16px 10px; }
  .page-title { font-size: 19px; }
  .content { padding: 16px 16px calc(var(--tabbar-h) + var(--safe-bottom) + 24px); }
  .bell-panel { position: fixed; left: 12px; right: 12px; top: calc(66px + var(--safe-top)); width: auto; max-height: 70vh; }

  .tabbar {
    display: flex; position: fixed; left: 0; right: 0; bottom: 0; z-index: 60;
    height: calc(var(--tabbar-h) + var(--safe-bottom)); padding: 6px 6px var(--safe-bottom);
    background: var(--panel); backdrop-filter: blur(20px); border-top: 1px solid var(--stroke);
  }
  .tab {
    flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
    border: 0; background: transparent; color: var(--muted-2); font-family: inherit; font-size: 11px; font-weight: 600;
    cursor: pointer; border-radius: 12px; transition: color .2s;
  }
  .tab.router-link-active, .tab.active { color: var(--brand); }
  [data-theme='dark'] .tab.router-link-active, [data-theme='dark'] .tab.active { color: var(--info-fg); }
  .tab-ico { position: relative; display: grid; place-items: center; width: 52px; height: 30px; border-radius: 99px; transition: background .25s; }
  .tab.router-link-active .tab-ico, .tab.active .tab-ico { background: var(--info-bg); }
  .tab-dot { position: absolute; top: -3px; right: 6px; min-width: 17px; height: 17px; padding: 0 4px; border-radius: 99px;
    background: var(--c-red); color: #fff; font-size: 10px; display: grid; place-items: center; }

  .sheet-backdrop { display: block; position: fixed; inset: 0; z-index: 70; background: rgba(4, 6, 15, .55); backdrop-filter: blur(6px); }
  .sheet {
    position: absolute; left: 0; right: 0; bottom: 0; padding: 10px 16px calc(18px + var(--safe-bottom));
    background: var(--panel-solid); border-radius: 24px 24px 0 0; border-top: 1px solid var(--stroke-strong);
    display: flex; flex-direction: column; gap: 14px; max-height: 88vh; overflow-y: auto;
  }
  .sheet-handle { width: 40px; height: 5px; border-radius: 99px; background: var(--stroke-strong); margin: 0 auto 4px; }
  .sheet-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .sheet-item {
    display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 14px 6px; border-radius: 16px;
    background: var(--card-2); border: 1px solid var(--stroke); font-size: 12.5px; font-weight: 600; text-align: center;
  }
  .sheet-item.router-link-active { border-color: var(--brand); background: var(--info-bg); }
  .sheet-ico { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; background: var(--info-bg); color: var(--brand); }
  [data-theme='dark'] .sheet-ico { color: var(--info-fg); }
  .sheet-actions { display: flex; flex-direction: column; gap: 8px; }
  .sheet-enter-active { transition: transform .35s cubic-bezier(.16,1,.3,1); }
  .sheet-leave-active { transition: transform .2s ease; }
  .sheet-enter-from, .sheet-leave-to { transform: translateY(100%); }
}
</style>
