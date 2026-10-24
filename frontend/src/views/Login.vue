<template>
  <div class="login-wrap">
    <div class="glow g1"></div>
    <div class="glow g2"></div>

    <div class="login-card animate-in">
      <button class="btn ghost sm theme-toggle" type="button" @click="toggleTheme" :title="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'">
        <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
      </button>
      <div class="brand">
        <div class="logo"><Icon name="code" :size="26" :stroke-width="2.2" /></div>
        <div>
          <div class="brand-name">IT Hub<span class="grad-text">Pro</span></div>
          <div class="muted small">Задачи, проекты и финансы</div>
        </div>
      </div>

      <h1 class="h1" style="margin-top: 26px">Вход в систему</h1>
      <p class="muted" style="margin-top: 6px">Войдите как суперадмин или рабочий</p>

      <form @submit.prevent="submit" style="margin-top: 22px">
        <div class="field">
          <label>Логин</label>
          <input v-model="username" class="input" placeholder="admin" autofocus />
        </div>
        <div class="field">
          <label>Пароль</label>
          <input v-model="password" type="password" class="input" placeholder="••••••••" />
        </div>

        <transition name="pop">
          <div v-if="error" class="badge red" style="margin: 6px 0 2px">{{ error }}</div>
        </transition>

        <button class="btn primary" style="width: 100%; margin-top: 16px" :disabled="loading">
          <span v-if="loading" class="spinner"></span>
          <span v-else class="row gap-8">Войти <Icon name="arrow-right" :size="18" /></span>
        </button>
      </form>

      <div class="hint">
        <div>Демо-доступы:</div>
        <div class="row gap-8 wrap mt-8">
          <button class="btn sm ghost" type="button" @click="fill('admin','admin12345')">admin</button>
          <button class="btn sm ghost" type="button" @click="fill('aidos','worker12345')">рабочий: aidos</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import { theme, toggleTheme } from '../theme'
import Icon from '../components/Icon.vue'

const auth = useAuth()
const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

function fill(u, p) { username.value = u; password.value = p }

async function submit() {
  error.value = ''
  loading.value = true
  try {
    const user = await auth.login(username.value.trim(), password.value)
    router.push(user.role === 'admin' ? '/dashboard' : '/tasks')
  } catch (e) {
    if (e.response) {
      error.value = e.response.status === 401
        ? 'Неверный логин или пароль'
        : `Ошибка сервера (${e.response.status})`
    } else {
      error.value = 'Сервер недоступен. Запущен ли backend на :8000?'
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh; display: grid; place-items: center; padding: 24px; position: relative; overflow: hidden;
}
.glow { position: absolute; border-radius: 50%; filter: blur(100px); opacity: .35; }
.g1 { width: 460px; height: 460px; background: #6366f1; top: -120px; right: -80px; }
.g2 { width: 420px; height: 420px; background: #22d3ee; bottom: -140px; left: -100px; opacity: .18; }
.login-card {
  position: relative; z-index: 1; width: 100%; max-width: 420px;
  background: var(--card);
  border: 1px solid var(--stroke-strong); border-radius: 24px; padding: 34px;
  box-shadow: var(--shadow);
}
.theme-toggle { position: absolute; top: 18px; right: 18px; width: 38px; height: 38px; padding: 0; }
.brand { display: flex; align-items: center; gap: 14px; }
.logo {
  width: 52px; height: 52px; border-radius: 15px; display: grid; place-items: center; color: #fff;
  background: var(--grad-brand); box-shadow: 0 10px 30px -10px rgba(99,102,241,.7);
}
.brand-name { font-weight: 800; font-size: 20px; letter-spacing: -.02em; }
@media (max-width: 480px) { .login-card { padding: 26px 20px; } }
.hint { margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--stroke); font-size: 13px; color: var(--muted); }
</style>
