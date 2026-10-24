import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuth } from './stores/auth'

import Login from './views/Login.vue'
import AdminLayout from './views/admin/AdminLayout.vue'
import Dashboard from './views/admin/Dashboard.vue'
import Projects from './views/admin/Projects.vue'
import ProjectDetail from './views/admin/ProjectDetail.vue'
import Users from './views/admin/Users.vue'
import History from './views/admin/History.vue'
import Finance from './views/admin/Finance.vue'
import Servers from './views/admin/Servers.vue'
import Renewals from './views/admin/Renewals.vue'
import Settings from './views/admin/Settings.vue'
import WorkerHome from './views/worker/WorkerHome.vue'
import TesterHome from './views/tester/TesterHome.vue'

const routes = [
  { path: '/login', component: Login, meta: { public: true } },
  {
    path: '/',
    component: AdminLayout,
    meta: { role: 'admin' },
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', component: Dashboard },
      { path: 'projects', component: Projects },
      { path: 'projects/:id', component: ProjectDetail },
      { path: 'users', component: Users },
      { path: 'workers', redirect: '/users' },
      { path: 'finance', component: Finance },
      { path: 'servers', component: Servers },
      { path: 'renewals', component: Renewals },
      { path: 'history', component: History },
      { path: 'settings', component: Settings },
    ],
  },
  { path: '/me', component: WorkerHome, meta: { role: 'worker' } },
  { path: '/tester', component: TesterHome, meta: { role: 'tester' } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuth()
  if (to.meta.public) return true
  if (!auth.isAuthenticated) return '/login'
  // у каждой роли свой раздел; роли совмещаются, поэтому проверяем «есть ли такая роль»
  const role = to.matched.map(r => r.meta.role).find(Boolean)
  // сессия со старым форматом пользователя (одна роль) — просим войти заново
  if (!auth.roles.length) { auth.logout(); return '/login' }
  if (role && !auth.hasRole(role)) return auth.home
  return true
})

export default router
