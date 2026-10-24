import axios from 'axios'
import { ref } from 'vue'

// Всплывающая ошибка (показывается в App.vue)
export const toast = ref('')
let toastTimer = null
export function showError(message) {
  toast.value = message
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 6000)
}

// Понятный текст ошибки из ответа API (бэкенд всегда кладёт его в `detail`)
export function errorMessage(e, fallback = 'Не удалось выполнить действие') {
  const data = e?.response?.data
  if (typeof data?.detail === 'string') return data.detail
  if (!e?.response) return 'Нет связи с сервером'
  return fallback
}

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    if (error.response && error.response.status === 401) {
      // сбрасываем и localStorage, и реактивное состояние стора
      const { useAuth } = await import('./stores/auth')
      try { useAuth().logout() } catch { localStorage.removeItem('access') }
      if (location.hash !== '#/login') location.hash = '#/login'
    } else if (!error.config?.silentError && error.config?.method !== 'get') {
      // ошибки изменяющих запросов показываем всегда, если страница не обрабатывает их сама
      showError(errorMessage(error))
    }
    return Promise.reject(error)
  }
)

// Форматирование денег в тенге: 1 250 000 ₸
export function money(value) {
  const n = Number(value || 0)
  return n.toLocaleString('ru-RU', { maximumFractionDigits: 0 }).replace(/,/g, ' ') + ' ₸'
}

export function formatDate(d) {
  if (!d) return '—'
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

export default api
