<template>
  <!-- показывается только тем, у кого больше одной роли -->
  <nav v-if="auth.cabinets.length > 1" class="cab-switch" :class="{ vertical }">
    <router-link v-for="c in auth.cabinets" :key="c.to" :to="c.to" class="cab"
      :class="{ on: isActive(c) }" :title="c.label">
      <Icon :name="c.icon" :size="15" /> <span>{{ c.label }}</span>
    </router-link>
  </nav>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { useAuth } from '../stores/auth'
import Icon from './Icon.vue'

defineProps({ vertical: Boolean })
const auth = useAuth()
const route = useRoute()

// админка — это все её вложенные страницы, кабинеты — отдельные адреса
const isActive = (c) => (c.role === 'admin' ? !['/me', '/tester'].includes(route.path) : route.path === c.to)
</script>

<style scoped>
.cab-switch { display: flex; gap: 4px; padding: 4px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); }
.cab-switch.vertical { flex-direction: column; }
.cab { display: flex; align-items: center; gap: 7px; padding: 8px 12px; border-radius: 9px; font-size: 13px; font-weight: 600; color: var(--muted); white-space: nowrap; transition: background .2s, color .2s; }
.cab:hover { color: var(--text); background: var(--hover); }
.cab.on { background: var(--brand); color: #fff; }
@media (max-width: 760px) { .cab-switch:not(.vertical) .cab span { display: none; } }
</style>
