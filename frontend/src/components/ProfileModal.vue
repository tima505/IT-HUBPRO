<template>
  <Modal :model-value="modelValue" eyebrow="Профиль" title="Мои данные" @update:model-value="$emit('update:modelValue', $event)">
    <div class="grid-2">
      <div class="field"><label>Логин</label><input :value="auth.user?.username" class="input" disabled /></div>
      <div class="field"><label>Роли</label><input :value="auth.user?.roles_display" class="input" disabled /></div>
    </div>
    <div class="grid-2">
      <div class="field"><label>ФИО</label><input v-model="form.full_name" class="input" placeholder="Имя Фамилия" /></div>
      <div class="field"><label>Телефон</label><input v-model="form.phone" class="input" placeholder="+7 700 000 00 00" /></div>
    </div>

    <div class="pw-block">
      <div class="muted small" style="margin-bottom: 8px">Смена пароля — оставьте пустым, если менять не нужно</div>
      <div class="grid-2">
        <div class="field"><label>Текущий пароль</label><input v-model="form.current_password" type="password" class="input" autocomplete="current-password" /></div>
        <div class="field"><label>Новый пароль</label><input v-model="form.new_password" type="password" class="input" placeholder="минимум 6 символов" autocomplete="new-password" /></div>
      </div>
    </div>

    <transition name="pop"><div v-if="error" class="badge red" style="margin-top: 10px">{{ error }}</div></transition>
    <transition name="pop"><div v-if="saved" class="badge green" style="margin-top: 10px">Сохранено</div></transition>

    <div class="row between mt-16">
      <button class="btn ghost" @click="$emit('update:modelValue', false)">Закрыть</button>
      <button class="btn primary" :disabled="busy" @click="save">
        <span v-if="busy" class="spinner"></span><span v-else>Сохранить</span>
      </button>
    </div>
  </Modal>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import api from '../api'
import { useAuth } from '../stores/auth'
import Modal from './Modal.vue'

const props = defineProps({ modelValue: Boolean })
defineEmits(['update:modelValue'])
const auth = useAuth()

const form = reactive({ full_name: '', phone: '', current_password: '', new_password: '' })
const busy = ref(false)
const error = ref('')
const saved = ref(false)

watch(() => props.modelValue, (open) => {
  if (!open) return
  Object.assign(form, { full_name: auth.user?.full_name || '', phone: auth.user?.phone || '', current_password: '', new_password: '' })
  error.value = ''; saved.value = false
})

async function save() {
  busy.value = true; error.value = ''; saved.value = false
  try {
    const body = { full_name: form.full_name.trim(), phone: form.phone.trim() }
    if (form.new_password) Object.assign(body, { current_password: form.current_password, new_password: form.new_password })
    const { data } = await api.patch('/auth/me/', body)
    auth.setUser(data)
    form.current_password = ''; form.new_password = ''
    saved.value = true
  } catch (e) {
    error.value = e.response?.data?.detail || 'Не удалось сохранить'
  } finally { busy.value = false }
}
</script>

<style scoped>
.pw-block { margin-top: 12px; padding-top: 14px; border-top: 1px solid var(--stroke); }
.input:disabled { opacity: .65; cursor: not-allowed; }
</style>
