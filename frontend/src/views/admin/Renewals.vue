<template>
  <div>
    <p class="muted" style="margin-bottom: 20px">
      Ежемесячные проекты. Когда до оплаты остаётся 3 дня или наступает последний день —
      приходит уведомление. После оплаты клиентом нажмите «Оплачено».
    </p>

    <transition-group name="list" tag="div" class="cards">
      <div v-for="p in due" :key="p.id" class="rcard card" :class="{ urgent: p.days_left <= 0 }">
        <div class="row between">
          <div>
            <div class="muted small">{{ p.worker_name }}</div>
            <h3 class="r-name">{{ p.name }}</h3>
          </div>
          <span class="badge" :class="p.days_left <= 0 ? 'red pulse' : (p.days_left <= 3 ? 'amber' : 'gray')">
            {{ p.days_left < 0 ? 'просрочено' : (p.days_left === 0 ? 'сегодня' : `через ${p.days_left} дн.`) }}
          </span>
        </div>

        <div class="r-amount">
          <div class="muted small">К оплате за месяц</div>
          <div class="mono" style="font-size: 24px; font-weight: 800">{{ money(p.monthly_amount) }}</div>
        </div>

        <div class="row between muted small">
          <span>След. оплата: {{ formatDate(p.monthly_next_due) }}</span>
        </div>

        <button class="btn green" style="width: 100%; margin-top: 6px" :disabled="busy === p.id" @click="pay(p)">
          <span v-if="busy === p.id" class="spinner"></span>
          <span v-else class="row gap-8"><Icon name="check-circle" :size="16" /> Оплачено — сдвинуть на месяц</span>
        </button>
      </div>
    </transition-group>

    <div v-if="!due.length" class="card center muted gap-8" style="padding: 50px">
      <Icon name="check-circle" :size="18" /> Нет ежемесячных проектов, требующих оплаты
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api, { money, formatDate } from '../../api'
import Icon from '../../components/Icon.vue'

const emit = defineEmits(['changed'])
const due = ref([])
const busy = ref(null)

async function pay(p) {
  busy.value = p.id
  try {
    await api.post(`/projects/${p.id}/pay_monthly/`, {})
    await load(); emit('changed')
  } finally { busy.value = null }
}

async function load() { due.value = (await api.get('/projects/due_monthly/')).data }
onMounted(load)
</script>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.rcard { display: flex; flex-direction: column; gap: 14px; transition: border-color .2s; }
.rcard.urgent { border-color: var(--c-red); }
.r-name { margin: 4px 0 0; font-size: 18px; font-weight: 700; }
.r-amount { padding: 14px; border-radius: 12px; background: var(--input-bg); }
</style>
