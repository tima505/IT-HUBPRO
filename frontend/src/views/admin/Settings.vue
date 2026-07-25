<template>
  <div>
    <h1 class="h1">Настройки</h1>
    <p class="muted mt-8" style="margin-bottom: 24px">Глобальные финансовые настройки системы</p>

    <div v-if="loaded" class="settings-grid animate-in">
      <!-- Фонд 1 -->
      <div class="card">
        <h2 class="h2" style="margin-bottom: 16px">
          <Icon name="percent" :size="18" /> Фонд 1
        </h2>
        <div class="field">
          <label>Название</label>
          <input v-model="form.fund1_name" class="input" />
        </div>
        <div class="field mt-12">
          <label>Процент (%)</label>
          <input v-model="form.fund1_rate" type="number" step="0.01" class="input" />
        </div>
        <div class="hint mt-8">
          <Icon name="info" :size="14" /> Текущая ставка: <b>{{ form.fund1_rate }}%</b>
        </div>
      </div>

      <!-- Фонд 2 -->
      <div class="card">
        <h2 class="h2" style="margin-bottom: 16px">
          <Icon name="percent" :size="18" /> Фонд 2
        </h2>
        <div class="field">
          <label>Название</label>
          <input v-model="form.fund2_name" class="input" />
        </div>
        <div class="field mt-12">
          <label>Процент (%)</label>
          <input v-model="form.fund2_rate" type="number" step="0.01" class="input" />
        </div>
        <div class="hint mt-8">
          <Icon name="info" :size="14" /> Текущая ставка: <b>{{ form.fund2_rate }}%</b>
        </div>
      </div>
    </div>

    <!-- Живой предпросмотр -->
    <div v-if="loaded" class="card mt-24 animate-in d2" style="max-width: 600px">
      <h2 class="h2" style="margin-bottom: 12px">Предпросмотр распределения</h2>
      <p class="muted small" style="margin-bottom: 16px">Если поступит 100 000 ₸:</p>
      <div class="preview-grid">
        <div class="preview-item">
          <span class="muted small">{{ form.fund1_name }}</span>
          <span class="mono" style="font-weight: 700">{{ money(100000 * (Number(form.fund1_rate) || 0) / 100) }}</span>
        </div>
        <div class="preview-item">
          <span class="muted small">{{ form.fund2_name }}</span>
          <span class="mono" style="font-weight: 700">{{ money(100000 * (Number(form.fund2_rate) || 0) / 100) }}</span>
        </div>
        <div class="preview-item">
          <span class="muted small">Остаток (для компании + рабочего)</span>
          <span class="mono" style="font-weight: 700; color: var(--accent)">{{ money(100000 * (1 - (Number(form.fund1_rate) || 0) / 100 - (Number(form.fund2_rate) || 0) / 100)) }}</span>
        </div>
      </div>
    </div>

    <div class="mt-24">
      <button class="btn primary" :disabled="busy" @click="save">
        <span v-if="busy" class="spinner"></span>
        <span v-else><Icon name="check" :size="16" /> Сохранить настройки</span>
      </button>
      <span v-if="saved" class="muted small" style="margin-left: 12px; color: var(--success)">✓ Сохранено!</span>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api, { money } from '../../api'
import Icon from '../../components/Icon.vue'

const loaded = ref(false)
const busy = ref(false)
const saved = ref(false)
const form = reactive({ fund1_rate: '', fund1_name: '', fund2_rate: '', fund2_name: '' })

async function load() {
  const { data } = await api.get('/settings/')
  Object.assign(form, data)
  loaded.value = true
}

async function save() {
  busy.value = true
  saved.value = false
  try {
    await api.put('/settings/', { ...form })
    saved.value = true
    setTimeout(() => saved.value = false, 3000)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 700px; }
.hint { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--muted); }
.preview-grid { display: flex; flex-direction: column; gap: 10px; }
.preview-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-radius: 10px; background: var(--input-bg); border: 1px solid var(--stroke); }
@media (max-width: 700px) { .settings-grid { grid-template-columns: 1fr; } }
</style>
