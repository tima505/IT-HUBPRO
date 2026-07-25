<template>
  <div v-if="fin">
    <!-- Три корзины (кликабельны — открывают детализацию) -->
    <div class="buckets">
      <button class="bucket card animate-in d1 company" @click="openBreakdown('company', 'Деньги компании')">
        <div class="b-top"><span class="b-ico"><Icon name="bank" :size="22" /></span><span class="badge green">основной</span></div>
        <div class="b-label">Деньги компании</div>
        <div class="b-value mono">{{ money(fin.company.balance) }}</div>
        <div class="b-flow muted small">
          <span>↑ {{ money(fin.company.income) }}</span>
          <span>↓ {{ money(fin.company.expense) }}</span>
        </div>
        <span class="b-hint"><Icon name="arrow-right" :size="14" /> детализация</span>
      </button>

      <button class="bucket card animate-in d2 f20" @click="openBreakdown('fund20', settings.fund1_name)">
        <div class="b-top"><span class="b-ico"><Icon name="percent" :size="22" /></span><span class="badge blue">{{ settings.fund1_rate }}%</span></div>
        <div class="b-label">{{ settings.fund1_name }}</div>
        <div class="b-value mono">{{ money(fin.fund20.balance) }}</div>
        <div class="b-flow muted small">
          <span>↑ {{ money(fin.fund20.income) }}</span>
          <span>↓ {{ money(fin.fund20.expense) }}</span>
        </div>
        <span class="b-hint"><Icon name="arrow-right" :size="14" /> детализация</span>
      </button>

      <button class="bucket card animate-in d3 f5" @click="openBreakdown('fund5', settings.fund2_name)">
        <div class="b-top"><span class="b-ico"><Icon name="percent" :size="22" /></span><span class="badge blue">{{ settings.fund2_rate }}%</span></div>
        <div class="b-label">{{ settings.fund2_name }}</div>
        <div class="b-value mono">{{ money(fin.fund5.balance) }}</div>
        <div class="b-flow muted small">
          <span>↑ {{ money(fin.fund5.income) }}</span>
          <span>↓ {{ money(fin.fund5.expense) }}</span>
        </div>
        <span class="b-hint"><Icon name="arrow-right" :size="14" /> детализация</span>
      </button>
    </div>

    <div class="grid-3 mt-24">
      <StatCard class="animate-in d4" label="Всего поступлений" :value="fin.total_income" icon="trending-up" color="#2563eb" />
      <StatCard class="animate-in d5" label="Выплачено рабочим" :value="fin.worker_payouts" icon="user" color="#d97706" />
      <StatCard class="animate-in d6" label="Расходы на серверы" :value="fin.server_expense" icon="server" color="#dc2626" />
    </div>

    <div class="card mt-24 animate-in d6">
      <h2 class="h2" style="margin-bottom: 6px">Как работает распределение</h2>
      <p class="muted small" style="margin-top: 0">С каждого поступления автоматически отделяется:</p>
      <div class="rules">
        <div class="rule"><span class="dot purple"></span> <b>{{ settings.fund1_rate }}%</b> → {{ settings.fund1_name }}</div>
        <div class="rule"><span class="dot blue"></span> <b>{{ settings.fund2_rate }}%</b> → {{ settings.fund2_name }}</div>
        <div class="rule"><span class="dot amber"></span> <b>доля рабочего</b> → фикс. суммы за бету и сдачу (старт без доли)</div>
        <div class="rule"><span class="dot green"></span> <b>остаток</b> → деньги компании</div>
      </div>
    </div>

    <!-- Детализация корзины -->
    <Modal v-model="modal" class="wide" eyebrow="Детализация" :title="detailTitle">
      <div v-if="loading" class="center" style="padding: 30px"><span class="spinner"></span></div>
      <div v-else-if="bd">
        <!-- Приход -->
        <div class="row between" style="margin-bottom: 8px">
          <h3 class="h2">Откуда пришли деньги</h3>
          <span class="badge green">+ {{ money(bd.income_total) }}</span>
        </div>
        <div class="dtable">
          <div class="dt-row dt-head"><span>Источник</span><span>Тип</span><span>Дата</span><span class="ta-r">В эту корзину</span></div>
          <div v-for="(it, i) in bd.income" :key="'i'+i" class="dt-row">
            <span><b>{{ it.source }}</b></span>
            <span class="muted">{{ it.detail }}</span>
            <span class="muted mono">{{ formatDate(it.date) }}</span>
            <span class="ta-r mono">{{ money(it.amount) }} <span class="muted small">из {{ money(it.base_amount) }}</span></span>
          </div>
          <div v-if="!bd.income.length" class="dt-empty muted">Поступлений пока нет</div>
        </div>

        <!-- Расход -->
        <div class="row between" style="margin: 22px 0 8px">
          <h3 class="h2">На что потрачено</h3>
          <span class="badge red">− {{ money(bd.expense_total) }}</span>
        </div>
        <div class="dtable">
          <div class="dt-row dt-exp dt-head"><span>Назначение</span><span>Тип</span><span>Дата</span><span class="ta-r">Сумма</span></div>
          <div v-for="(it, i) in bd.expense" :key="'e'+i" class="dt-row dt-exp">
            <span><b>{{ it.source }}</b></span>
            <span class="muted">{{ it.detail }}</span>
            <span class="muted mono">{{ formatDate(it.date) }}</span>
            <span class="ta-r mono">{{ money(it.amount) }}</span>
          </div>
          <div v-if="!bd.expense.length" class="dt-empty muted">Расходов из этой корзины нет</div>
        </div>

        <div class="row between total-row mt-16">
          <b>Текущий остаток</b>
          <b class="mono" style="font-size: 18px">{{ money(bd.income_total - bd.expense_total) }}</b>
        </div>
      </div>
    </Modal>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api, { money, formatDate } from '../../api'
import StatCard from '../../components/StatCard.vue'
import Icon from '../../components/Icon.vue'
import Modal from '../../components/Modal.vue'

const fin = ref(null)
const settings = ref({ fund1_name: 'Фонд 20%', fund1_rate: 20, fund2_name: 'Фонд 5%', fund2_rate: 5 })
const modal = ref(false)
const loading = ref(false)
const bd = ref(null)
const detailTitle = ref('')

onMounted(async () => {
  const [f, s] = await Promise.all([api.get('/finance/'), api.get('/settings/')])
  fin.value = f.data
  settings.value = s.data
})

async function openBreakdown(bucket, title) {
  detailTitle.value = title
  bd.value = null
  modal.value = true
  loading.value = true
  try {
    bd.value = (await api.get('/finance/', { params: { bucket } })).data
  } finally { loading.value = false }
}
</script>

<style scoped>
.buckets { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.bucket {
  position: relative; overflow: hidden; text-align: left; cursor: pointer; font: inherit; color: inherit;
  transition: transform .18s ease, box-shadow .2s ease, border-color .2s;
}
.bucket:hover { transform: translateY(-3px); border-color: var(--stroke-strong); box-shadow: var(--shadow); }
.bucket::after { content: ''; position: absolute; inset: 0; opacity: .18; pointer-events: none; }
.bucket.company::after { background: radial-gradient(200px 120px at 100% 0, #059669, transparent 70%); }
.bucket.f20::after { background: radial-gradient(200px 120px at 100% 0, #4f46e5, transparent 70%); }
.bucket.f5::after { background: radial-gradient(200px 120px at 100% 0, #0284c7, transparent 70%); }
.b-top { display: flex; justify-content: space-between; align-items: center; }
.b-ico { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 12px; background: var(--card-2); color: var(--brand); }
.bucket.company .b-ico { color: #059669; }
.bucket.f20 .b-ico { color: #4f46e5; }
.bucket.f5 .b-ico { color: #0284c7; }
.b-label { margin-top: 18px; color: var(--muted); font-size: 14px; }
.b-value { font-size: 32px; font-weight: 800; margin-top: 4px; letter-spacing: -.02em; }
.b-flow { display: flex; gap: 16px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--stroke); }
.b-hint { position: absolute; top: 18px; right: 18px; display: none; align-items: center; gap: 4px; font-size: 12px; color: var(--brand); font-weight: 600; }
.bucket:hover .b-hint { display: inline-flex; }
.bucket:hover .b-top .badge { opacity: 0; }
.rules { display: grid; grid-template-columns: repeat(2,1fr); gap: 10px; margin-top: 14px; }
.rule { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); font-size: 14px; }
.dot { width: 12px; height: 12px; border-radius: 50%; }
.dot.purple { background: #4f46e5; } .dot.blue { background: #0284c7; } .dot.amber { background: #d97706; } .dot.green { background: #059669; }

/* таблица детализации */
.dtable { border: 1px solid var(--stroke); border-radius: 12px; overflow: hidden; }
.dt-row { display: grid; grid-template-columns: 2fr 1.1fr 1fr 1.4fr; gap: 10px; padding: 11px 14px; align-items: center; font-size: 14px; border-bottom: 1px solid var(--stroke); }
.dt-row:last-child { border-bottom: none; }
.dt-head { background: var(--input-bg); font-size: 12px; text-transform: uppercase; letter-spacing: .03em; color: var(--muted-2); font-weight: 600; }
.dt-row:not(.dt-head):hover { background: var(--hover); }
.ta-r { text-align: right; }
.dt-empty { padding: 16px; text-align: center; }
.total-row { padding: 14px 16px; border-radius: 12px; background: var(--input-bg); border: 1px solid var(--stroke); }
@media (max-width: 900px) { .buckets, .rules { grid-template-columns: 1fr; } }
</style>
