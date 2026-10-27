import { ref, watch } from 'vue'
import { useAuth } from '../stores/auth'

// Черновик формы в браузере: всё, что набрано, переживает уход на другую страницу,
// перезагрузку и закрытие вкладки. Ключ — пользователь + форма (например, «project:new»).
const PREFIX = 'draft:'

function storageKey(name) {
  const auth = useAuth()
  return `${PREFIX}${auth.user?.id || 'anon'}:${name}`
}

export function useDraft(name, state, { exclude = [], when = () => true } = {}) {
  const key = storageKey(name)
  const restoredAt = ref(null)   // когда был сохранён восстановленный черновик
  let paused = true               // не пишем, пока форма не заполнена исходными данными

  function snapshot() {
    const data = {}
    for (const [k, v] of Object.entries(state)) if (!exclude.includes(k)) data[k] = v
    return data
  }

  /** Подставить черновик в форму. Вызывать после загрузки исходных данных. Возвращает true, если был. */
  function restore() {
    let saved = null
    try { saved = JSON.parse(localStorage.getItem(key) || 'null') } catch { /* битый или недоступен */ }
    if (saved?.data) {
      Object.assign(state, saved.data)
      restoredAt.value = saved.at
    }
    paused = false
    return !!saved?.data
  }

  let timer = null
  watch(state, () => {
    if (paused || !when()) return
    clearTimeout(timer)
    timer = setTimeout(() => {
      try { localStorage.setItem(key, JSON.stringify({ at: Date.now(), data: snapshot() })) } catch { /* приватный режим */ }
    }, 250)
  }, { deep: true })

  /** Удалить черновик (после сохранения или по кнопке «Очистить»). */
  function clear() {
    clearTimeout(timer)
    try { localStorage.removeItem(key) } catch { /* ignore */ }
    restoredAt.value = null
  }

  return { restore, clear, restoredAt }
}

export function draftAge(at) {
  if (!at) return ''
  const min = Math.round((Date.now() - at) / 60000)
  if (min < 1) return 'только что'
  if (min < 60) return `${min} мин назад`
  const h = Math.round(min / 60)
  if (h < 24) return `${h} ч назад`
  return new Date(at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}
