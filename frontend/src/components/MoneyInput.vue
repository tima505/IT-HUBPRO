<template>
  <div class="money-input" :class="[size, { focus }]">
    <input
      ref="el"
      :value="display"
      class="mi-field"
      inputmode="numeric"
      autocomplete="off"
      :placeholder="placeholder"
      :id="id"
      @input="onInput"
      @focus="focus = true"
      @blur="focus = false"
    />
    <span class="mi-cur">₸</span>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

// Сумма в тенге: показывает «1 250 000», наружу отдаёт число (или null, если пусто)
const props = defineProps({
  modelValue: { type: [Number, String, null], default: null },
  placeholder: { type: String, default: '0' },
  size: { type: String, default: '' }, // '' | 'lg'
  id: String,
})
const emit = defineEmits(['update:modelValue'])
const el = ref(null)
const focus = ref(false)

const fmt = (n) => (n === null || n === '' || n === undefined ? '' : Number(n).toLocaleString('ru-RU').replace(/ /g, ' '))
const display = computed(() => fmt(props.modelValue))

function onInput(e) {
  const input = e.target
  const digitsBefore = input.value.slice(0, input.selectionStart).replace(/\D/g, '').length
  const digits = input.value.replace(/\D/g, '').replace(/^0+(?=\d)/, '').slice(0, 13)
  const value = digits ? Number(digits) : null
  emit('update:modelValue', value)
  // сохраняем позицию курсора после расстановки пробелов
  const text = fmt(value)
  input.value = text
  let pos = 0, seen = 0
  while (pos < text.length && seen < digitsBefore) { if (/\d/.test(text[pos])) seen++; pos++ }
  input.setSelectionRange(pos, pos)
}

defineExpose({ focus: () => el.value?.focus() })
</script>

<style scoped>
.money-input {
  display: flex; align-items: center; gap: 8px; padding: 0 14px; border-radius: var(--radius-sm);
  background: var(--input-bg); border: 1px solid var(--stroke); transition: border .2s, box-shadow .2s;
}
.money-input.focus { border-color: var(--brand); box-shadow: 0 0 0 4px var(--info-bg); }
.mi-field {
  flex: 1; min-width: 0; border: 0; outline: none; background: transparent; color: var(--text);
  font: 600 15px var(--font); font-variant-numeric: tabular-nums; padding: 11px 0;
}
.mi-field::placeholder { color: var(--muted-2); font-weight: 500; }
.mi-cur { color: var(--muted); font-weight: 600; }
.money-input.lg { padding: 0 18px; border-radius: 16px; }
.money-input.lg .mi-field { font-size: 30px; font-weight: 800; letter-spacing: -.02em; padding: 14px 0; }
.money-input.lg .mi-cur { font-size: 24px; }
@media (max-width: 900px) { .mi-field { font-size: 16px; } .money-input.lg .mi-field { font-size: 26px; } }
</style>
