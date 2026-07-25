import { ref } from 'vue'

const stored = localStorage.getItem('theme') || 'dark'
export const theme = ref(stored)

export function applyTheme(value) {
  document.documentElement.setAttribute('data-theme', value)
  localStorage.setItem('theme', value)
  theme.value = value
}

export function toggleTheme() {
  applyTheme(theme.value === 'dark' ? 'light' : 'dark')
}

// применить при загрузке
applyTheme(theme.value)
