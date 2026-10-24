<template>
  <div class="mp">
    <div class="hero-row">
      <div class="hero card animate-in">
        <div class="eyebrow">Выплачено вам</div>
        <div class="hero-val mono">{{ money(data.total_earned) }}</div>
        <div class="muted small">по всем вашим проектам</div>
      </div>
      <div class="hero card owed animate-in d1">
        <div class="eyebrow">Компания ещё должна</div>
        <div class="hero-val mono">{{ money(data.total_owed) }}</div>
        <div class="muted small">будет выплачено по договорённости</div>
      </div>
    </div>

    <h2 class="h2">Мои проекты</h2>

    <div v-if="loaded && !data.projects.length" class="card empty">
      <div class="empty-ico"><Icon name="folder" :size="22" /></div>Пока вам не назначено ни одного проекта
    </div>

    <transition-group name="list" tag="div" class="cards">
      <article v-for="p in data.projects" :key="p.id" class="pcard card">
        <div class="row between gap-8">
          <StatusBadge :status="p.status" />
          <DeadlineBadge :status="p.deadline_status" />
        </div>
        <div>
          <h3 class="p-name">{{ p.name }}</h3>
          <div v-if="p.client_name" class="muted small"><Icon name="briefcase" :size="13" /> {{ p.client_name }}</div>
        </div>
        <p v-if="p.description" class="muted small desc">{{ p.description }}</p>

        <div class="earn">
          <div class="row between"><span class="muted small">Договорились</span><b class="mono">{{ money(p.worker_amount) }}</b></div>
          <div class="row between"><span class="muted small">Выплачено</span><b class="mono ok">{{ money(p.worker_paid) }}</b></div>
          <div v-if="Number(p.worker_amount) > 0" class="progress"><span :style="{ width: Math.min(100, p.worker_paid / p.worker_amount * 100) + '%' }"></span></div>
          <div class="row between"><span class="muted small">Осталось получить</span><b class="mono" :class="Number(p.worker_debt) > 0 ? 'warn' : 'ok'">{{ money(p.worker_debt) }}</b></div>
          <div v-if="p.payouts.length" class="payouts">
            <div v-for="po in p.payouts" :key="po.id" class="po">
              <span class="muted small">{{ formatDate(po.date) }}<span v-if="po.note"> · {{ po.note }}</span></span>
              <b class="mono small">{{ money(po.amount) }}</b>
            </div>
          </div>
        </div>

        <div class="dates">
          <div><span class="muted small">Старт</span><b>{{ formatDate(p.start_date) }}</b></div>
          <div><span class="muted small">Дедлайн</span><b>{{ formatDate(p.deadline_date) }}</b></div>
          <div><span class="muted small">Сдал</span><b>{{ p.finished_date ? formatDate(p.finished_date) : '—' }}</b></div>
        </div>

        <div v-if="p.status === 'active'" class="foot">
          <button v-if="!p.finished_date" class="btn sm green" @click="finish(p)"><Icon name="check" :size="14" /> Отметить сдачу</button>
          <button v-else class="btn sm ghost" @click="unfinish(p)">Отменить отметку сдачи</button>
        </div>

        <div v-if="p.servers.length" class="srv-line muted small">
          <Icon name="server" :size="14" /> Сервер до {{ formatDate(p.servers[0].expiry_date) }}
          <span class="badge" :class="p.servers[0].days_left <= 7 ? 'amber' : 'green'">{{ p.servers[0].days_left }} дн.</span>
        </div>
      </article>
    </transition-group>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api, { money, formatDate } from '../../api'
import StatusBadge from '../../components/StatusBadge.vue'
import Icon from '../../components/Icon.vue'
import DeadlineBadge from '../../components/DeadlineBadge.vue'

const data = ref({ projects: [], total_earned: 0, total_owed: 0 })
const loaded = ref(false)

async function loadData() {
  data.value = (await api.get('/worker/dashboard/')).data
  loaded.value = true
}
async function finish(p) { await api.post(`/projects/${p.id}/finish/`, {}); await loadData() }
async function unfinish(p) { await api.post(`/projects/${p.id}/finish/`, { clear: true }); await loadData() }

onMounted(loadData)
</script>

<style scoped>
.mp { display: flex; flex-direction: column; gap: 16px; max-width: 1100px; }
.hero-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.hero { position: relative; overflow: hidden; }
.hero::after { content: ''; position: absolute; inset: 0; background: radial-gradient(300px 160px at 90% -10%, rgba(99,102,241,.22), transparent 70%); pointer-events: none; }
.hero-val { font-size: clamp(26px, 6vw, 38px); font-weight: 800; letter-spacing: -.03em; margin: 6px 0 2px; color: var(--ok-fg); }
.owed .hero-val { color: var(--warn-fg); }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(310px, 100%), 1fr)); gap: 14px; position: relative; }
.pcard { display: flex; flex-direction: column; gap: 12px; }
.p-name { margin: 0 0 4px; font-size: 17px; font-weight: 700; }
.desc { margin: 0; line-height: 1.5; }
.earn { padding: 12px 14px; border-radius: 14px; background: var(--card-2); border: 1px solid var(--stroke); display: flex; flex-direction: column; gap: 8px; }
.ok { color: var(--ok-fg); } .warn { color: var(--warn-fg); }
.payouts { display: flex; flex-direction: column; gap: 4px; padding-top: 8px; border-top: 1px dashed var(--stroke-strong); }
.po { display: flex; justify-content: space-between; gap: 8px; }
.dates { display: flex; justify-content: space-between; gap: 8px; }
.dates div { display: flex; flex-direction: column; gap: 3px; }
.foot { padding-top: 10px; border-top: 1px solid var(--stroke); }
.srv-line { display: flex; align-items: center; gap: 8px; padding-top: 10px; border-top: 1px solid var(--stroke); }
@media (max-width: 640px) { .hero-row { grid-template-columns: 1fr; } }
</style>
