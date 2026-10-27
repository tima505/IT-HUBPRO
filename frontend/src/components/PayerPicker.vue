<template>
  <div class="payer">
    <div v-if="!fundOnly" class="segmented full">
      <button type="button" :class="{ active: paidBy === 'company' }" @click="$emit('update:paidBy', 'company')">
        <Icon name="bank" :size="15" /> Платит компания
      </button>
      <button type="button" :class="{ active: paidBy === 'client' }" @click="$emit('update:paidBy', 'client')">
        <Icon name="user" :size="15" /> Платит клиент
      </button>
    </div>
    <template v-if="paidBy === 'company'">
      <div v-if="!fundOnly" class="muted small">Из какого фонда списать</div>
      <div class="buckets">
        <button v-for="b in buckets" :key="b.key" type="button" class="bucket"
                :class="{ on: paidFrom === b.key, short: amount && b.balance !== null && amount > b.balance }"
                @click="$emit('update:paidFrom', b.key)">
          <span>{{ b.name }}</span>
          <b v-if="b.balance !== null" class="mono">{{ money(b.balance) }}</b>
        </button>
      </div>
      <div v-if="shortage" class="badge red">В «{{ shortage.name }}» не хватает {{ money(amount - shortage.balance) }}</div>
    </template>
    <div v-else class="note small">Клиент оплачивает сервер сам — сумма сохраняется для учёта, деньги компании и фонды не тратятся.</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { money } from '../api'
import Icon from './Icon.vue'

// Кто платит (компания / клиент) и, если компания, — из какого фонда
const props = defineProps({
  paidBy: { type: String, default: 'company' },
  paidFrom: { type: String, default: 'company' },
  amount: { type: Number, default: null },
  // [{ key, name, balance }] — balance может быть null, если не загружен
  buckets: { type: Array, required: true },
  fundOnly: { type: Boolean, default: false }, // только выбор фонда, без «платит клиент»
})
defineEmits(['update:paidBy', 'update:paidFrom'])

const shortage = computed(() => {
  const b = props.buckets.find(x => x.key === props.paidFrom)
  return b && b.balance !== null && props.amount && props.amount > b.balance ? b : null
})
</script>

<style scoped>
.payer { display: flex; flex-direction: column; gap: 10px; }
.segmented.full { display: flex; }
.segmented.full button { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
.buckets { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.bucket { display: flex; flex-direction: column; gap: 3px; padding: 9px 11px; text-align: left; border-radius: 12px; cursor: pointer;
  border: 1px solid var(--stroke); background: var(--card-2); color: var(--muted); font: 500 12.5px var(--font); transition: border-color .2s; }
.bucket b { color: var(--text); font-size: 14px; }
.bucket.on { border-color: var(--brand); background: var(--info-bg); }
.bucket.short b { color: var(--bad-fg); }
.note { padding: 10px 12px; border-radius: 12px; background: var(--info-bg); color: var(--text); line-height: 1.45; }
@media (max-width: 520px) { .buckets { grid-template-columns: 1fr; } }
</style>
