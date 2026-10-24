<template>
  <header class="wtop">
    <div class="row gap-12">
      <div class="logo"><Icon name="briefcase" :size="22" /></div>
      <div>
        <div class="brand-name">IT HubPro</div>
        <div class="muted small">{{ subtitle }}</div>
      </div>
    </div>
    <div class="row gap-12">
      <button class="btn ghost icon-btn" @click="toggleTheme" :title="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'">
        <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="19" />
      </button>
      <CabinetSwitch />
      <NotificationBell @tick="$emit('tick')" />
      <button class="user-chip" title="Мой профиль" @click="profile = true">
        <div class="avatar">{{ initials }}</div>
        <div class="chip-txt">
          <div style="font-weight: 600">{{ auth.user?.full_name || auth.user?.username }}</div>
          <div class="muted small">{{ roleLabel }}</div>
        </div>
      </button>
      <button class="btn ghost sm" @click="logout"><Icon name="logout" :size="16" /> Выйти</button>
    </div>

    <ProfileModal v-model="profile" />
  </header>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import { theme, toggleTheme } from '../theme'
import Icon from './Icon.vue'
import NotificationBell from './NotificationBell.vue'
import CabinetSwitch from './CabinetSwitch.vue'
import ProfileModal from './ProfileModal.vue'

defineProps({ subtitle: String, roleLabel: String })
defineEmits(['tick'])

const auth = useAuth()
const router = useRouter()
const profile = ref(false)

const initials = computed(() => {
  const n = auth.user?.full_name || auth.user?.username || '?'
  return n.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase()
})

function logout() { auth.logout(); router.push('/login') }
</script>

<style scoped>
.wtop { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 18px 32px; border-bottom: 1px solid var(--stroke); position: sticky; top: 0; background: var(--panel); z-index: 10; }
.logo { width: 44px; height: 44px; border-radius: 13px; display: grid; place-items: center; color: #fff; background: var(--grad-brand); }
.brand-name { font-weight: 800; letter-spacing: -.02em; }
.user-chip { display: flex; align-items: center; gap: 10px; padding: 4px 10px 4px 4px; border-radius: 14px; border: 1px solid transparent; background: transparent; color: var(--text); cursor: pointer; text-align: left; font: inherit; transition: background .2s, border-color .2s; }
.user-chip:hover { background: var(--hover); border-color: var(--stroke); }
.avatar { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; font-weight: 700; background: var(--grad-brand); color: #fff; }
@media (max-width: 640px) { .wtop { padding: 14px 16px; } .chip-txt { display: none; } }
</style>
