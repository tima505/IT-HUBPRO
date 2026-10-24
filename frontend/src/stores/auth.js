import { defineStore } from 'pinia'
import api from '../api'

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
    isWorker: (s) => (s.user?.roles || []).includes('worker'),
    isTester: (s) => (s.user?.roles || []).includes('tester'),
    // стартовая страница: админу — дашборд, остальным — свои задачи
    home() { return this.isAdmin ? '/dashboard' : '/tasks' },
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
