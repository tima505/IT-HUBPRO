<template>
  <div class="pl">
    <!-- Сводка -->
    <div class="summary">
      <div class="s-item"><span class="muted small">Сумма проектов</span><b class="mono">{{ money(totals.price) }}</b></div>
      <div class="s-item"><span class="muted small">Оплачено</span><b class="mono ok">{{ money(totals.paid) }}</b></div>
      <div class="s-item debt"><span class="small">Долг клиентов</span><b class="mono">{{ money(totals.debt) }}</b></div>
    </div>

    <div class="toolbar">
      <div class="search">
        <Icon name="search" :size="17" />
        <input v-model="q" class="input" placeholder="Проект, клиент, телефон…" />
      </div>
      <div class="segmented filters">
        <button v-for="f in filters" :key="f.v" :class="{ active: filter === f.v }" @click="filter = f.v">
          {{ f.label }} <span class="mono cnt">{{ count(f.v) }}</span>
        </button>
      </div>
      <router-link to="/projects/new" class="btn primary"><Icon name="plus" :size="18" /> Новый проект</router-link>
    </div>

    <transition-group name="list" tag="div" class="cards">
      <article v-for="p in filtered" :key="p.id" class="proj card" @click="$router.push(`/projects/${p.id}`)">
        <div class="row between gap-8">
          <StatusBadge :status="p.status" />
          <span v-if="p.has_monthly" class="badge amber">+ {{ money(p.monthly_amount) }}/мес</span>
        </div>
        <div>
          <h3 class="p-name">{{ p.name }}</h3>
          <div class="p-sub muted small">
            <span v-if="p.client_name"><Icon name="briefcase" :size="13" /> {{ p.client_name }}</span>
            <span><Icon name="user" :size="13" /> {{ p.worker_name || p.worker_username }}</span>
          </div>
        </div>

        <div v-if="Number(p.price) > 0" class="p-money">
          <div class="row between">
            <span class="mono price">{{ money(p.price) }}</span>
            <span v-if="Number(p.debt) > 0" class="badge red">долг {{ money(p.debt) }}</span>
            <span v-else class="badge green"><Icon name="check" :size="12" /> оплачен</span>
          </div>
          <div class="progress" :class="{ ok: p.paid_percent === 100 }"><span :style="{ width: (p.paid_percent || 0) + '%' }"></span></div>
          <div class="row between muted small">
            <span>оплачено {{ money(p.paid) }}</span><span class="mono">{{ p.paid_percent || 0 }}%</span>
          </div>
        </div>
        <div v-else class="p-money muted small">Только ежемесячное обслуживание</div>

        <div class="p-foot muted small">
          <span class="row gap-4"><Icon name="flag" :size="13" /> {{ formatDate(p.deadline_date) }}</span>
          <DeadlineBadge v-if="p.status === 'active'" :status="p.deadline_status" />
        </div>
      </article>
    </transition-group>

    <div v-if="loaded && !filtered.length" class="card empty">
      <div class="empty-ico"><Icon name="folder" :size="22" /></div>
      {{ projects.length ? 'Ничего не найдено' : 'Проектов пока нет' }}
      <router-link v-if="!projects.length" to="/projects/new" class="btn primary sm"><Icon name="plus" :size="15" /> Создать первый</router-link>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api, { money, formatDate } from '../../api'
import StatusBadge from '../../components/StatusBadge.vue'
import DeadlineBadge from '../../components/DeadlineBadge.vue'
import Icon from '../../components/Icon.vue'

const projects = ref([])
const loaded = ref(false)
const q = ref('')
const filter = ref('all')
const filters = [
  { v: 'all', label: 'Все' },
  { v: 'active', label: 'В работе' },
  { v: 'debt', label: 'С долгом' },
  { v: 'done', label: 'Завершённые' },
]
const match = {
  all: () => true,
  active: (p) => p.status === 'active',
  debt: (p) => Number(p.debt) > 0,
  done: (p) => p.status === 'done',
}
const searched = computed(() => {
  const s = q.value.trim().toLowerCase()
  if (!s) return projects.value
  return projects.value.filter(p => [p.name, p.client_name, p.client_phone, p.worker_name].some(v => (v || '').toLowerCase().includes(s)))
})
const filtered = computed(() => searched.value.filter(match[filter.value]))
const count = (v) => searched.value.filter(match[v]).length
const totals = computed(() => projects.value.filter(p => p.status !== 'cancelled').reduce((t, p) => ({
  price: t.price + Number(p.price), paid: t.paid + Number(p.paid), debt: t.debt + Number(p.debt),
}), { price: 0, paid: 0, debt: 0 }))

onMounted(async () => {
  projects.value = (await api.get('/projects/')).data
  loaded.value = true
})
</script>

<style scoped>
.pl { display: flex; flex-direction: column; gap: 16px; }
.summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.s-item { display: flex; flex-direction: column; gap: 4px; padding: 14px 18px; border-radius: 16px; background: var(--card); border: 1px solid var(--stroke); min-width: 0; }
.s-item b { font-size: 22px; letter-spacing: -.02em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.s-item .ok { color: var(--ok-fg); }
.s-item.debt { background: var(--bad-bg); border-color: transparent; color: var(--bad-fg); }

.toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.search { position: relative; flex: 1 1 240px; }
.search .icon { position: absolute; left: 13px; top: 50%; transform: translateY(-50%); color: var(--muted-2); }
.search .input { padding-left: 38px; }
.filters { overflow-x: auto; scrollbar-width: none; max-width: 100%; }
.cnt { opacity: .6; margin-left: 2px; }

.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(310px, 100%), 1fr)); gap: 14px; position: relative; }
.proj { cursor: pointer; display: flex; flex-direction: column; gap: 14px; transition: transform .2s, border-color .2s, box-shadow .2s; }
.proj:hover { transform: translateY(-3px); border-color: var(--stroke-strong); box-shadow: var(--shadow); }
.p-name { margin: 0; font-size: 17px; font-weight: 700; letter-spacing: -.01em; }
.p-sub { display: flex; gap: 6px 14px; flex-wrap: wrap; margin-top: 6px; }
.p-sub span { display: inline-flex; align-items: center; gap: 5px; }
.p-money { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border-radius: 14px; background: var(--card-2); border: 1px solid var(--stroke); }
.price { font-size: 18px; font-weight: 800; letter-spacing: -.01em; }
.p-foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; padding-top: 10px; border-top: 1px solid var(--stroke); margin-top: auto; }

@media (max-width: 900px) {
  .summary { grid-template-columns: 1fr 1fr; }
  .summary .debt { grid-column: 1 / -1; order: -1; }
  .s-item b { font-size: 18px; }
  .toolbar .btn.primary { width: 100%; }
}
</style>
