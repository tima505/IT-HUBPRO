<template>
  <div class="wshell">
    <header class="wtop">
      <div class="row gap-12">
        <div class="logo"><Icon name="briefcase" :size="22" /></div>
        <div>
          <div class="brand-name">IT HubPro</div>
          <div class="muted small">кабинет рабочего</div>
        </div>
      </div>
      <div class="row gap-12">
        <button class="btn ghost icon-btn" @click="toggleTheme" :title="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'">
          <Icon :name="theme === 'dark' ? 'sun' : 'moon'" :size="19" />
        </button>
        <div class="user-chip">
          <div class="avatar">{{ initials }}</div>
          <div>
            <div style="font-weight: 600">{{ auth.user?.full_name || auth.user?.username }}</div>
            <div class="muted small">Рабочий</div>
          </div>
        </div>
        <button class="btn ghost sm" @click="logout"><Icon name="logout" :size="16" /> Выйти</button>
      </div>
    </header>

    <div class="wbody">
      <div class="hero card animate-in">
        <div class="eyebrow">Ваш заработок</div>
        <div class="hero-val mono">{{ money(data.total_earned) }}</div>
        <div class="muted">Всего начислено по завершённым этапам ваших проектов</div>
      </div>

      <h2 class="h2 mt-24" style="margin-bottom: 14px">Мои проекты</h2>

      <transition-group name="list" tag="div" class="cards">
        <div v-for="p in visibleProjects" :key="p.id" class="pcard card">
          <div class="row between">
            <StatusBadge :status="p.status" />
            <div class="row gap-4">
              <span v-if="p.has_stages" class="badge blue">Этапы</span>
              <span v-if="p.has_monthly" class="badge amber">Ежемесячная</span>
            </div>
          </div>
          <h3 class="p-name">{{ p.name }}</h3>

          <div class="earn" v-if="p.has_stages">
            <div class="row between">
              <span class="muted small">Старт</span>
              <span class="mono muted">без доли</span>
            </div>
            <div class="row between">
              <span class="muted small">Бета</span>
              <span class="mono">{{ money(p.worker_beta_amount) }}</span>
            </div>
            <div class="row between">
              <span class="muted small">Сдача</span>
              <span class="mono">{{ money(p.worker_final_amount) }}</span>
            </div>
            <div class="row between" style="margin-top: 8px; border-top: 1px solid var(--stroke); padding-top: 8px">
              <span class="muted small">Уже выплачено вам</span>
              <span class="mono" style="font-size: 16px; font-weight: 800; color: var(--warn-fg)">{{ money(p.totals.worker) }}</span>
            </div>
          </div>
          <div class="earn" v-if="p.has_monthly && !p.has_stages">
            <div class="muted small">Помесячный проект</div>
            <div class="muted small">Оплата вашей работы обсуждается отдельно.</div>
          </div>

          <div class="dates">
            <div><span class="muted small">Старт</span><b>{{ formatDate(p.start_date) }}</b></div>
            <div><span class="muted small">Дедлайн</span><b>{{ formatDate(p.deadline_date) }}</b></div>
            <div><span class="muted small">Сдал</span><b>{{ p.finished_date ? formatDate(p.finished_date) : '—' }}</b></div>
          </div>

          <div class="deadline-line">
            <DeadlineBadge :status="p.deadline_status" />
            <div v-if="p.status === 'active'">
              <button v-if="!p.finished_date" class="btn sm green" @click="finish(p)"><Icon name="check" :size="14" /> Отметить сдачу</button>
              <button v-else class="btn sm ghost" @click="unfinish(p)">Отменить</button>
            </div>
          </div>

          <div v-if="p.servers.length" class="srv-line muted small row gap-8">
            <Icon name="server" :size="14" /> Сервер до {{ formatDate(p.servers[0].expiry_date) }}
            <span class="badge" :class="p.servers[0].days_left <= 7 ? 'amber' : 'green'" style="margin-left: 6px">{{ p.servers[0].days_left }} дн.</span>
          </div>
        </div>
      </transition-group>

      <div v-if="hiddenCount" class="more-row">
        <button class="btn ghost more-btn" :class="{ open: expanded }" @click="expanded = !expanded">
          <Icon name="chevron-down" :size="18" class="chev" />
          {{ expanded ? 'Свернуть' : `Показать ещё ${hiddenCount}` }}
        </button>
      </div>

      <div v-if="!data.projects?.length" class="card center muted" style="padding: 50px">
        Пока вам не назначено ни одного проекта
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api, { money, formatDate } from '../../api'
import { useAuth } from '../../stores/auth'
import { theme, toggleTheme } from '../../theme'
import StatusBadge from '../../components/StatusBadge.vue'
import Icon from '../../components/Icon.vue'
import DeadlineBadge from '../../components/DeadlineBadge.vue'

const auth = useAuth()
const router = useRouter()
const data = ref({ projects: [], total_earned: 0 })

const VISIBLE_LIMIT = 3
const expanded = ref(false)
const visibleProjects = computed(() =>
  expanded.value ? data.value.projects : (data.value.projects || []).slice(0, VISIBLE_LIMIT)
)
const hiddenCount = computed(() => Math.max(0, (data.value.projects?.length || 0) - VISIBLE_LIMIT))

async function loadData() { data.value = (await api.get('/worker/dashboard/')).data }
async function finish(p) { await api.post(`/projects/${p.id}/finish/`, {}); await loadData() }
async function unfinish(p) { await api.post(`/projects/${p.id}/finish/`, { clear: true }); await loadData() }

const initials = computed(() => {
  const n = auth.user?.full_name || auth.user?.username || '?'
  return n.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase()
})

function logout() { auth.logout(); router.push('/login') }

onMounted(loadData)
</script>

<style scoped>
.wshell { min-height: 100vh; }
.wtop { display: flex; align-items: center; justify-content: space-between; padding: 18px 32px; border-bottom: 1px solid var(--stroke); position: sticky; top: 0; background: var(--panel); z-index: 10; }
.logo { width: 44px; height: 44px; border-radius: 13px; display: grid; place-items: center; color: #fff; background: var(--grad-brand); }
.brand-name { font-weight: 800; letter-spacing: -.02em; }
.user-chip { display: flex; align-items: center; gap: 10px; }
.avatar { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; font-weight: 700; background: var(--grad-brand); color: #fff; }
.wbody { max-width: 1100px; margin: 0 auto; padding: 28px 32px 60px; }
.hero { position: relative; overflow: hidden; }
.hero::after { content: ''; position: absolute; inset: 0; background: radial-gradient(300px 160px at 90% -10%, rgba(37,99,235,.18), transparent 70%); pointer-events: none; }
.hero-val { font-size: 44px; font-weight: 800; letter-spacing: -.03em; margin: 8px 0; color: var(--brand); }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; position: relative; }
.pcard { transition: transform .25s cubic-bezier(.16,1,.3,1), border-color .25s, box-shadow .25s; }
.pcard:hover { transform: translateY(-3px); border-color: var(--stroke-strong); box-shadow: var(--shadow); }
.pcard { display: flex; flex-direction: column; gap: 12px; }
.p-name { margin: 0; font-size: 18px; font-weight: 700; }
.earn { padding: 14px; border-radius: 12px; background: var(--input-bg); display: flex; flex-direction: column; gap: 4px; }
.dates { display: flex; justify-content: space-between; }
.dates div { display: flex; flex-direction: column; gap: 3px; }
.more-row { display: flex; justify-content: center; margin-top: 20px; }
.more-btn { border-radius: 999px; padding: 11px 22px; }
.more-btn:hover { border-color: var(--brand); color: var(--brand); }
.more-btn .chev { transition: transform .35s cubic-bezier(.16,1,.3,1); }
.more-btn.open .chev { transform: rotate(180deg); }
.deadline-line { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-top: 10px; border-top: 1px solid var(--stroke); flex-wrap: wrap; }
.srv-line { padding-top: 10px; border-top: 1px solid var(--stroke); }
</style>
