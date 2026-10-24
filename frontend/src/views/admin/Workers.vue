<template>
  <div>
    <div class="row between" style="margin-bottom: 20px">
      <p class="muted">Создавайте рабочих и назначайте им проекты. У каждого свой вход в систему.</p>
      <button class="btn primary" @click="openCreate"><Icon name="plus" :size="18" /> Новый рабочий</button>
    </div>

    <transition-group name="list" tag="div" class="cards">
      <div v-for="w in workers" :key="w.id" class="wcard card">
        <div class="row between">
          <div class="avatar">{{ initials(w) }}</div>
          <button class="btn ghost sm icon-sm" @click="openEdit(w)"><Icon name="edit" :size="16" /></button>
        </div>
        <h3 class="wname">{{ w.full_name || w.username }}</h3>
        <div class="muted small">@{{ w.username }}</div>
        <div v-if="w.phone" class="muted small row gap-8"><Icon name="phone" :size="14" /> {{ w.phone }}</div>
        <div class="wstats">
          <div><div class="muted small">Проектов</div><b>{{ w.projects_count }}</b></div>
          <div><div class="muted small">Заработал</div><b class="mono">{{ money(w.total_earned) }}</b></div>
        </div>
      </div>
    </transition-group>

    <div v-if="!workers.length" class="card center muted" style="padding: 50px">Рабочих ещё нет</div>

    <Modal v-model="show" :eyebrow="editing ? 'Редактирование' : 'Новый рабочий'" :title="editing ? 'Изменить рабочего' : 'Создать рабочего'">
      <div class="grid-2">
        <div class="field"><label>ФИО *</label><input v-model="form.full_name" class="input" placeholder="Айдос Серіков" /></div>
        <div class="field"><label>Логин *</label><input v-model="form.username" class="input" placeholder="aidos" /></div>
      </div>
      <div class="grid-2">
        <div class="field"><label>Телефон</label><input v-model="form.phone" class="input" placeholder="+7 700 000 00 00" /></div>
        <div class="field"><label>{{ editing ? 'Новый пароль' : 'Пароль' }}</label><input v-model="form.password" class="input" :placeholder="editing ? 'оставьте пустым' : 'worker12345'" /></div>
      </div>
      <transition name="pop"><div v-if="error" class="badge red" style="margin-top: 8px">{{ error }}</div></transition>
      <div class="row between mt-16">
        <button class="btn ghost" @click="show = false">Отмена</button>
        <button class="btn primary" :disabled="busy || !form.username || !form.full_name" @click="save">
          <span v-if="busy" class="spinner"></span><span v-else>Сохранить</span>
        </button>
      </div>
    </Modal>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api, { money, errorMessage } from '../../api'
import Modal from '../../components/Modal.vue'
import Icon from '../../components/Icon.vue'

const workers = ref([])
const show = ref(false)
const busy = ref(false)
const error = ref('')
const editing = ref(null)
const form = reactive({ full_name: '', username: '', phone: '', password: '' })

function initials(w) { const n = w.full_name || w.username; return n.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase() }

function openCreate() { editing.value = null; Object.assign(form, { full_name: '', username: '', phone: '', password: '' }); error.value = ''; show.value = true }
function openEdit(w) { editing.value = w; Object.assign(form, { full_name: w.full_name, username: w.username, phone: w.phone, password: '' }); error.value = ''; show.value = true }

async function save() {
  busy.value = true; error.value = ''
  try {
    if (editing.value) await api.patch(`/workers/${editing.value.id}/`, form, { silentError: true })
    else await api.post('/workers/', form, { silentError: true })
    show.value = false; await load()
  } catch (e) {
    error.value = errorMessage(e, 'Проверьте поля (логин должен быть уникальным)')
  } finally { busy.value = false }
}

async function load() { workers.value = (await api.get('/workers/')).data }
onMounted(load)
</script>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
.wcard { display: flex; flex-direction: column; gap: 6px; transition: transform .2s, border-color .2s; }
.wcard:hover { transform: translateY(-3px); border-color: var(--stroke-strong); }
.avatar { width: 52px; height: 52px; border-radius: 15px; display: grid; place-items: center; font-weight: 800; font-size: 18px; background: var(--grad-brand); color: white; }
.wname { margin: 8px 0 0; font-size: 18px; font-weight: 700; }
.wstats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--stroke); }
</style>
