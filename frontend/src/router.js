import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuth } from './stores/auth'

import Login from './views/Login.vue'
import AppLayout from './views/AppLayout.vue'
const Dashboard = () => import('./views/admin/Dashboard.vue')
const Projects = () => import('./views/admin/Projects.vue')
const ProjectDetail = () => import('./views/admin/ProjectDetail.vue')
const ProjectForm = () => import('./views/admin/ProjectForm.vue')
const Debts = () => import('./views/admin/Debts.vue')
const Users = () => import('./views/admin/Users.vue')
const History = () => import('./views/admin/History.vue')
const Finance = () => import('./views/admin/Finance.vue')
const Servers = () => import('./views/admin/Servers.vue')
const Renewals = () => import('./views/admin/Renewals.vue')
const Settings = () => import('./views/admin/Settings.vue')
const MyProjects = () => import('./views/worker/MyProjects.vue')
const TesterHome = () => import('./views/tester/TesterHome.vue')
const Tasks = () => import('./views/Tasks.vue')
const Plan = () => import('./views/Plan.vue')
const Analytics = () => import('./views/Analytics.vue')

const admin = { role: 'admin' }

const routes = [
  { path: '/login', component: Login, meta: { public: true } },
  {
    path: '/',
    component: AppLayout,
    children: [
      { path: '', redirect: () => useAuth().home },
      // общие разделы — для любой роли
      { path: 'tasks', component: Tasks },
      { path: 'plan', component: Plan },
      { path: 'analytics', component: Analytics },
      // суперадмин
      { path: 'dashboard', component: Dashboard, meta: admin },
      { path: 'projects', component: Projects, meta: admin },
      { path: 'projects/new', component: ProjectForm, meta: admin },
      { path: 'projects/:id(\\d+)', component: ProjectDetail, meta: admin },
      { path: 'projects/:id(\\d+)/edit', component: ProjectForm, meta: admin },
      { path: 'debts', component: Debts, meta: admin },
      { path: 'users', component: Users, meta: admin },
      { path: 'workers', redirect: '/users' },
      { path: 'finance', component: Finance, meta: admin },
      { path: 'servers', component: Servers, meta: admin },
      { path: 'renewals', component: Renewals, meta: admin },
      { path: 'history', component: History, meta: admin },
      { path: 'settings', component: Settings, meta: admin },
      // рабочий и тестировщик
      { path: 'me', component: MyProjects, meta: { role: 'worker' } },
      { path: 'tester', component: TesterHome, meta: { role: 'tester' } },
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
  // сессия со старым форматом пользователя (одна роль) — просим войти заново
  if (!auth.roles.length) { auth.logout(); return '/login' }
  // у разделов своя роль; роли совмещаются, поэтому проверяем «есть ли такая роль»
  const role = to.matched.map(r => r.meta.role).find(Boolean)
  if (role && !auth.hasRole(role)) return auth.home
  return true
})

export default router
