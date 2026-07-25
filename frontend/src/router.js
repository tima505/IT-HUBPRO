import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuth } from './stores/auth'

import Login from './views/Login.vue'
import AdminLayout from './views/admin/AdminLayout.vue'
import Dashboard from './views/admin/Dashboard.vue'
import Projects from './views/admin/Projects.vue'
import ProjectDetail from './views/admin/ProjectDetail.vue'
import Workers from './views/admin/Workers.vue'
import Finance from './views/admin/Finance.vue'
import Servers from './views/admin/Servers.vue'
import Renewals from './views/admin/Renewals.vue'
import Settings from './views/admin/Settings.vue'
import WorkerHome from './views/worker/WorkerHome.vue'

const routes = [
  { path: '/login', component: Login, meta: { public: true } },
  {
    path: '/',
    component: AdminLayout,
    meta: { admin: true },
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', component: Dashboard },
      { path: 'projects', component: Projects },
      { path: 'projects/:id', component: ProjectDetail },
      { path: 'workers', component: Workers },
      { path: 'finance', component: Finance },
      { path: 'servers', component: Servers },
      { path: 'renewals', component: Renewals },
      { path: 'settings', component: Settings },
    ],
  },
  { path: '/me', component: WorkerHome, meta: { worker: true } },
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
  if (to.meta.admin && !auth.isAdmin) return '/me'
  if (to.meta.worker && auth.isAdmin) return '/dashboard'
  return true
})

export default router
