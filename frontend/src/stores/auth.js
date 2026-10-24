import { defineStore } from 'pinia'
import api from '../api'

export const CABINETS = [
  { role: 'admin', to: '/dashboard', label: 'Панель админа', icon: 'dashboard' },
  { role: 'worker', to: '/me', label: 'Мои проекты', icon: 'user' },
  { role: 'tester', to: '/tester', label: 'Проверка', icon: 'check-circle' },
]

export const useAuth = defineStore('auth', {
  state: () => ({
    // храним в реактивном состоянии, чтобы геттеры пересчитывались
    token: localStorage.getItem('access') || null,
    user: JSON.parse(localStorage.getItem('user') || 'null'),
  }),
  getters: {
    isAuthenticated: (s) => !!s.token,
    // роли совмещаются: ['admin', 'worker', 'tester'] в любом сочетании
    roles: (s) => s.user?.roles || [],
    isAdmin: (s) => (s.user?.roles || []).includes('admin'),
    // разделы, куда пользователю можно зайти, — для переключателя кабинетов
    cabinets: (s) => CABINETS.filter(c => (s.user?.roles || []).includes(c.role)),
    // стартовая страница: админка, затем кабинет рабочего, затем тестировщика
    home() { return this.cabinets[0]?.to || '/login' },
  },
  actions: {
    hasRole(role) { return this.roles.includes(role) },
    setUser(user) {
      localStorage.setItem('user', JSON.stringify(user))
      this.user = user
    },
    async login(username, password) {
      const { data } = await api.post('/auth/login/', { username, password })
      localStorage.setItem('access', data.access)
      localStorage.setItem('refresh', data.refresh)
      localStorage.setItem('user', JSON.stringify(data.user))
      this.token = data.access
      this.user = data.user
      return data.user
    },
    logout() {
      localStorage.removeItem('access')
      localStorage.removeItem('refresh')
      localStorage.removeItem('user')
      this.token = null
      this.user = null
    },
  },
})
