<template>
  <div class="shell">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="brand">
        <div class="logo"><Icon name="briefcase" :size="22" /></div>
        <div class="brand-txt">
          <div class="brand-name">IT HubPro</div>
          <div class="muted small">панель управления</div>
        </div>
      </div>

      <nav class="nav">
        <router-link v-for="item in nav" :key="item.to" :to="item.to" class="nav-item">
          <span class="nav-ico"><Icon :name="item.icon" :size="19" /></span>
          <span>{{ item.label }}</span>
          <span v-if="item.to === '/renewals' && dueCount" class="nav-count">{{ dueCount }}</span>
        </router-link>
      </nav>

      <div class="side-foot">
        <CabinetSwitch vertical style="margin-bottom: 10px" />
        <button class="user-chip" title="Мой профиль" @click="profile = true">
          <div class="avatar">{{ initials }}</div>
          <div class="grow" style="overflow: hidden">
            <div class="uname">{{ auth.user?.full_name || auth.user?.username }}</div>
            <div class="muted small">{{ auth.user?.roles_display }} · профиль</div>
          </div>
        </button>
        <button class="btn ghost sm" style="width: 100%; margin-top: 10px" @click="logout">
          <Icon name="logout" :size="16" /> Выйти
        </button>
      </div>
    </aside>

    <!-- Main -->
    <main class="main">
      <header class="topbar">
        <div>
          <div class="eyebrow">{{ pageEyebrow }}</div>
          <div class="page-title">{{ pageTitle }}</div>
        </div>

        <div class="row gap-12">
          <button class="btn ghost icon-btn" @click="toggleTheme" :title="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'">
            <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="19" />
          </button>

          <NotificationBell ref="bell" />
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

    <ProfileModal v-model="profile" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../../api'
import { useAuth } from '../../stores/auth'
import { theme, toggleTheme } from '../../theme'
import Icon from '../../components/Icon.vue'
import NotificationBell from '../../components/NotificationBell.vue'
import ProfileModal from '../../components/ProfileModal.vue'
import CabinetSwitch from '../../components/CabinetSwitch.vue'

const auth = useAuth()
const router = useRouter()
const route = useRoute()

const nav = [
  { to: '/dashboard', label: 'Дашборд', icon: 'dashboard' },
  { to: '/projects', label: 'Проекты', icon: 'folder' },
  { to: '/users', label: 'Пользователи', icon: 'users' },
  { to: '/finance', label: 'Финансы', icon: 'wallet' },
  { to: '/servers', label: 'Серверы', icon: 'server' },
  { to: '/renewals', label: 'Продления', icon: 'renew' },
  { to: '/history', label: 'История', icon: 'history' },
  { to: '/settings', label: 'Настройки', icon: 'edit' },
]

const titles = {
  '/dashboard': ['Обзор', 'Дашборд'],
  '/projects': ['Управление', 'Проекты'],
  '/users': ['Команда', 'Пользователи'],
  '/finance': ['Деньги', 'Финансы'],
  '/servers': ['Инфраструктура', 'Серверы'],
  '/renewals': ['Оплаты', 'Продление проектов'],
  '/history': ['Журнал', 'История'],
  '/settings': ['Система', 'Настройки'],
}
const pageEyebrow = computed(() => (titles[route.path]?.[0]) || 'Раздел')
const pageTitle = computed(() => (titles[route.path]?.[1]) || 'IT HubPro')

const initials = computed(() => {
  const n = auth.user?.full_name || auth.user?.username || '?'
  return n.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase()
})

const dueCount = ref(0)
const bell = ref(null)
const profile = ref(false)
let timer = null

async function refreshCounts() {
  bell.value?.refresh()
  try {
    const due = await api.get('/projects/due_monthly/')
    dueCount.value = due.data.filter(p => p.days_left <= 3).length
  } catch (e) { /* ignore */ }
}

function logout() {
  auth.logout()
  router.push('/login')
}

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
  display: flex; flex-direction: column; gap: 8px;
  background: var(--panel); border-right: 1px solid var(--stroke);
}
.brand { display: flex; align-items: center; gap: 12px; padding: 6px 8px 18px; }
.logo { width: 44px; height: 44px; border-radius: 13px; display: grid; place-items: center; color: #fff;
  background: var(--grad-brand); box-shadow: 0 8px 22px -10px rgba(37,99,235,.6); }
.brand-name { font-weight: 800; letter-spacing: -.02em; }
.nav { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
.nav-item {
  display: flex; align-items: center; gap: 12px; padding: 11px 14px; border-radius: 12px;
  color: var(--muted); font-weight: 600; font-size: 14px; transition: all .2s; position: relative;
}
.nav-item:hover { background: var(--hover); color: var(--text); }
.nav-item.router-link-active {
  background: var(--info-bg); color: var(--brand);
}
.nav-ico { display: grid; place-items: center; width: 22px; }
.nav-count { margin-left: auto; background: var(--c-red); color: #fff; font-size: 11px; font-weight: 700;
  min-width: 20px; height: 20px; border-radius: 999px; display: grid; place-items: center; padding: 0 6px; }
.side-foot { margin-top: auto; }
.user-chip { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px; border-radius: 14px; background: var(--card-2); border: 1px solid var(--stroke); color: var(--text); font: inherit; text-align: left; cursor: pointer; transition: border-color .2s, background .2s; }
.user-chip:hover { border-color: var(--brand); background: var(--hover); }
.avatar { width: 38px; height: 38px; border-radius: 11px; display: grid; place-items: center; font-weight: 700; background: var(--grad-brand); color: #fff; }
.uname { font-weight: 600; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.main { display: flex; flex-direction: column; min-width: 0; }
.topbar { display: flex; align-items: center; justify-content: space-between; padding: 20px 32px; border-bottom: 1px solid var(--stroke); position: sticky; top: 0; z-index: 20; background: var(--panel); }
.page-title { font-size: 22px; font-weight: 800; letter-spacing: -.02em; margin-top: 3px; }
.content { padding: 28px 32px 48px; }

@media (max-width: 900px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar { position: fixed; z-index: 60; transform: translateX(-100%); }
}
</style>
