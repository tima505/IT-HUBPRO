<template>
  <div class="debts">
    <div class="totals">
      <button class="t-card" :class="{ on: tab === 'clients' }" @click="tab = 'clients'">
        <span class="t-ico bad"><Icon name="briefcase" :size="20" /></span>
        <span class="grow"><span class="muted small">Клиенты должны нам</span><b class="mono">{{ money(data.clients_total) }}</b></span>
        <span class="badge gray">{{ data.clients.length }}</span>
      </button>
      <button class="t-card" :class="{ on: tab === 'workers' }" @click="tab = 'workers'">
        <span class="t-ico warn"><Icon name="users" :size="20" /></span>
        <span class="grow"><span class="muted small">Мы должны рабочим</span><b class="mono">{{ money(data.workers_total) }}</b></span>
        <span class="badge gray">{{ data.workers.length }}</span>
      </button>
    </div>

    <!-- Клиенты -->
    <template v-if="tab === 'clients'">
      <div v-if="loaded && !data.clients.length" class="card empty">
        <div class="empty-ico"><Icon name="check-circle" :size="22" /></div>Все клиенты рассчитались
      </div>
      <div class="list">
        <article v-for="c in data.clients" :key="c.client_name + c.client_phone" class="card debtor">
          <div class="d-head">
            <span class="avatar">{{ initials(c.client_name) }}</span>
            <div class="grow">
              <b class="d-name">{{ c.client_name }}</b>
              <a v-if="c.client_phone" class="phone" :href="`tel:${c.client_phone.replace(/[^\d+]/g, '')}`" @click.stop>
                <Icon name="phone" :size="13" /> {{ c.client_phone }}
              </a>
              <span v-else class="muted small">телефон не указан</span>
            </div>
            <div class="d-sum">
              <span class="muted small">долг</span>
              <b class="mono bad">{{ money(c.debt) }}</b>
            </div>
          </div>
          <div class="progress"><span :style="{ width: pct(c.paid, c.price) + '%' }"></span></div>
          <div class="muted small">оплачено {{ money(c.paid) }} из {{ money(c.price) }}</div>
          <div class="projects">
            <router-link v-for="p in c.projects" :key="p.id" :to="`/projects/${p.id}`" class="pr">
              <span class="grow ellipsis"><b>{{ p.name }}</b>
                <span class="muted small hide-m"> · {{ p.last_payment ? 'посл. оплата ' + formatDate(p.last_payment) : 'оплат не было' }}</span>
              </span>
              <span class="mono pr-debt">{{ money(p.debt) }}</span>
              <Icon name="chevron-right" :size="16" class="muted" />
            </router-link>
          </div>
        </article>
      </div>
    </template>

    <!-- Рабочие -->
    <template v-else>
      <div v-if="loaded && !data.workers.length" class="card empty">
        <div class="empty-ico"><Icon name="check-circle" :size="22" /></div>Всем рабочим всё выплачено
      </div>
      <div class="list">
        <article v-for="w in data.workers" :key="w.worker_id" class="card debtor">
          <div class="d-head">
            <span class="avatar">{{ initials(w.worker_name) }}</span>
            <b class="grow d-name">{{ w.worker_name }}</b>
            <div class="d-sum">
              <span class="muted small">должны</span>
              <b class="mono warn">{{ money(w.debt) }}</b>
            </div>
          </div>
          <div class="projects">
            <router-link v-for="p in w.projects" :key="p.id" :to="`/projects/${p.id}`" class="pr">
              <span class="grow ellipsis"><b>{{ p.name }}</b>
                <span class="muted small"> · выплачено {{ money(p.paid) }} из {{ money(p.owed) }}</span>
              </span>
              <span class="mono pr-debt warn">{{ money(p.debt) }}</span>
              <Icon name="chevron-right" :size="16" class="muted" />
            </router-link>
          </div>
        </article>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api, { money, formatDate } from '../../api'
import Icon from '../../components/Icon.vue'

const data = ref({ clients: [], workers: [], clients_total: 0, workers_total: 0 })
const loaded = ref(false)
const tab = ref('clients')

const pct = (a, b) => (Number(b) > 0 ? Math.min(100, Number(a) / Number(b) * 100) : 0)
function initials(n = '') {
  return n.replace(/[«»"'()]/g, '').split(' ').filter(s => !['ТОО', 'ИП', 'АО'].includes(s)).map(s => s[0]).slice(0, 2).join('').toUpperCase() || '?'
}

onMounted(async () => {
  data.value = (await api.get('/debts/')).data
  loaded.value = true
})
</script>

<style scoped>
.debts { display: flex; flex-direction: column; gap: 16px; }
.totals { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.t-card {
  display: flex; align-items: center; gap: 14px; padding: 16px 18px; border-radius: 18px; cursor: pointer; text-align: left;
  background: var(--card); border: 1px solid var(--stroke); color: var(--text); font-family: inherit; transition: all .2s;
}
.t-card:hover { border-color: var(--stroke-strong); }
.t-card.on { border-color: var(--brand); box-shadow: 0 0 0 4px var(--info-bg); }
.t-card .grow { display: flex; flex-direction: column; gap: 2px; }
.t-card b { font-size: 24px; letter-spacing: -.02em; }
.t-ico { width: 44px; height: 44px; border-radius: 13px; display: grid; place-items: center; flex-shrink: 0; }
.t-ico.bad { background: var(--bad-bg); color: var(--bad-fg); }
.t-ico.warn { background: var(--warn-bg); color: var(--warn-fg); }

.list { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(420px, 100%), 1fr)); gap: 14px; }
.debtor { display: flex; flex-direction: column; gap: 10px; }
.d-head { display: flex; align-items: center; gap: 12px; }
.d-name { font-size: 16px; display: block; }
.phone { display: inline-flex; align-items: center; gap: 5px; font-size: 13px; color: var(--brand); margin-top: 2px; }
[data-theme='dark'] .phone { color: var(--info-fg); }
.d-sum { display: flex; flex-direction: column; align-items: flex-end; }
.d-sum b { font-size: 19px; }
.bad { color: var(--bad-fg); } .warn { color: var(--warn-fg); }
.projects { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.pr { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 12px; background: var(--card-2); border: 1px solid var(--stroke); transition: border-color .2s; }
.pr:hover { border-color: var(--brand); }
.pr-debt { font-weight: 700; }

@media (max-width: 640px) {
  .hide-m { display: none; }
  .totals { grid-template-columns: 1fr; }
  .t-card b { font-size: 20px; }
}
</style>
