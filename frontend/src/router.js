import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuth } from './stores/auth'

import Login from './views/Login.vue'
import AppLayout from './views/AppLayout.vue'
const Dashboard = () => import('./views/admin/Dashboard.vue')
const Projects = () => import('./views/admin/Projects.vue')
const ProjectDetail = () => import('./views/admin/ProjectDetail.vue')
const ProjectForm = () => import('./views/admin/ProjectForm.vue')
const Debts = () => import('./views/admin/Debts.vue')
const Workers = () => import('./views/admin/Workers.vue')
const Finance = () => import('./views/admin/Finance.vue')
const Servers = () => import('./views/admin/Servers.vue')
const Renewals = () => import('./views/admin/Renewals.vue')
const Settings = () => import('./views/admin/Settings.vue')
const MyProjects = () => import('./views/worker/MyProjects.vue')
const Tasks = () => import('./views/Tasks.vue')
const Analytics = () => import('./views/Analytics.vue')

const admin = { admin: true }
const worker = { worker: true }

const routes = [
  { path: '/login', component: Login, meta: { public: true } },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: () => (useAuth().isAdmin ? '/dashboard' : '/tasks') },
      // общие разделы
      { path: 'tasks', component: Tasks },
      { path: 'analytics', component: Analytics },
      // суперадмин
      { path: 'dashboard', component: Dashboard, meta: admin },
      { path: 'projects', component: Projects, meta: admin },
      { path: 'projects/new', component: ProjectForm, meta: admin },
      { path: 'projects/:id(\\d+)', component: ProjectDetail, meta: admin },
      { path: 'projects/:id(\\d+)/edit', component: ProjectForm, meta: admin },
      { path: 'debts', component: Debts, meta: admin },
      { path: 'workers', component: Workers, meta: admin },
      { path: 'finance', component: Finance, meta: admin },
      { path: 'servers', component: Servers, meta: admin },
      { path: 'renewals', component: Renewals, meta: admin },
      { path: 'settings', component: Settings, meta: admin },
      // рабочий
      { path: 'me', component: MyProjects, meta: worker },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  const auth = useAuth()
  if (to.meta.public) return true
  if (!auth.isAuthenticated) return '/login'
  if (to.meta.admin && !auth.isAdmin) return '/tasks'
  if (to.meta.worker && auth.isAdmin) return '/dashboard'
  return true
})

export default router
