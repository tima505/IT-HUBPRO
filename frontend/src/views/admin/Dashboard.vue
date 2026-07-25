<template>
  <div>
    <div class="grid-4">
      <StatCard class="animate-in d1" label="Всего поступлений" :value="fin.total_income" icon="trending-up" color="#2563eb" />
      <StatCard class="animate-in d2" label="Деньги компании" :value="fin.company?.balance" icon="bank" color="#059669" />
      <StatCard class="animate-in d3" :label="settings.fund1_name" :value="fin.fund20?.balance" icon="percent" color="#4f46e5" />
      <StatCard class="animate-in d4" :label="settings.fund2_name" :value="fin.fund5?.balance" icon="percent" color="#0284c7" />
    </div>

    <div class="grid-stats mt-24">
      <StatCard class="animate-in d3" label="Выплаты рабочим" :value="fin.worker_payouts" icon="user" color="#d97706" />
      <StatCard class="animate-in d4" label="Расходы на серверы" :value="fin.server_expense" icon="server" color="#dc2626" />
      <StatCard class="animate-in d5" label="Активных проектов" :value="activeCount" icon="folder" color="#2563eb" :is-money="false" />
      <StatCard class="animate-in d6" label="Рабочих в команде" :value="workersCount" icon="users" color="#4f46e5" :is-money="false" />
    </div>

    <div class="two-col mt-24">
      <div class="card animate-in d5">
        <div class="row between" style="margin-bottom: 14px">
          <h2 class="h2">Последние проекты</h2>
          <router-link to="/projects" class="btn ghost sm">Все проекты →</router-link>
        </div>
        <table class="table">
          <thead><tr><th>Проект</th><th>Рабочий</th><th>Тип</th><th>Статус</th></tr></thead>
          <tbody>
            <tr v-for="p in recent" :key="p.id" @click="$router.push(`/projects/${p.id}`)" style="cursor: pointer">
              <td><b>{{ p.name }}</b></td>
              <td class="muted">{{ p.worker_name }}</td>
              <td>
                <span v-if="p.has_stages" class="badge blue">Этапы</span>
                <span v-if="p.has_monthly" class="badge amber">Ежемесячно</span>
              </td>
              <td><StatusBadge :status="p.status" /></td>
            </tr>
            <tr v-if="!recent.length"><td colspan="4" class="muted center" style="padding: 24px">Проектов пока нет</td></tr>
          </tbody>
        </table>
      </div>

      <div class="card animate-in d6">
        <h2 class="h2" style="margin-bottom: 14px">Скоро продление</h2>
        <div v-if="!due.length" class="muted small center gap-8" style="padding: 30px 0"><Icon name="check-circle" :size="16" /> Нет приближающихся оплат</div>
        <div v-for="p in due" :key="p.id" class="due-row">
          <div>
            <div style="font-weight: 600">{{ p.name }}</div>
            <div class="muted small">{{ money(p.monthly_amount) }} / мес</div>
          </div>
          <span class="badge" :class="p.days_left <= 0 ? 'red pulse' : (p.days_left <= 3 ? 'amber' : 'gray')">
            {{ p.days_left <= 0 ? 'Сегодня' : `${p.days_left} дн.` }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import api, { money } from '../../api'
import StatCard from '../../components/StatCard.vue'
import StatusBadge from '../../components/StatusBadge.vue'
import Icon from '../../components/Icon.vue'

const fin = ref({})
const settings = ref({ fund1_name: 'Фонд 20%', fund2_name: 'Фонд 5%' })
const projects = ref([])
const workersCount = ref(0)
const due = ref([])

const recent = computed(() => projects.value.slice(0, 6))
const activeCount = computed(() => projects.value.filter(p => p.status === 'active').length)

onMounted(async () => {
  const [f, p, w, d, s] = await Promise.all([
    api.get('/finance/'),
    api.get('/projects/'),
    api.get('/workers/'),
    api.get('/projects/due_monthly/'),
    api.get('/settings/'),
  ])
  fin.value = f.data
  projects.value = p.data
  workersCount.value = w.data.length
  due.value = d.data.slice(0, 6)
  settings.value = s.data
})
</script>

<style scoped>
.grid-4, .grid-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.two-col { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; }
.due-row { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid rgba(255,255,255,.06); }
.due-row:last-child { border-bottom: none; }
@media (max-width: 1100px) { .grid-4, .grid-stats { grid-template-columns: repeat(2,1fr); } .two-col { grid-template-columns: 1fr; } }
</style>
