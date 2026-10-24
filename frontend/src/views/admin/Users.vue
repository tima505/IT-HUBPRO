<template>
  <div>
    <div class="row between wrap gap-12" style="margin-bottom: 20px">
      <div class="row gap-8 wrap">
        <button v-for="f in filters" :key="f.v" class="btn sm" :class="{ primary: filter === f.v }" @click="filter = f.v">
          {{ f.label }} <span class="count">{{ f.count }}</span>
        </button>
      </div>
      <button class="btn primary" @click="openCreate"><Icon name="plus" :size="18" /> Новый пользователь</button>
    </div>

    <FilterBar v-model:search="q" placeholder="Имя, логин, телефон…" :count="filtered.length" :total="byRoleTab.length" />

    <transition-group name="list" tag="div" class="cards">
      <div v-for="u in filtered" :key="u.id" class="ucard card">
        <div class="row between">
          <div class="avatar" :class="u.roles[0]">{{ initials(u) }}</div>
          <div class="row gap-4">
            <button class="btn ghost sm icon-sm" title="Изменить" @click="openEdit(u)"><Icon name="edit" :size="16" /></button>
            <button v-if="u.id !== auth.user?.id" class="btn ghost sm icon-sm" title="Удалить" @click="askDelete(u)"><Icon name="trash" :size="16" /></button>
          </div>
        </div>
        <h3 class="uname">{{ u.full_name || u.username }}</h3>
        <div class="row gap-8 wrap">
          <span v-for="r in u.roles" :key="r" class="badge" :class="roleCls[r]">{{ roleLabel[r] }}</span>
          <span v-if="u.id === auth.user?.id" class="badge gray">это вы</span>
        </div>
        <div class="muted small">@{{ u.username }}</div>
        <div v-if="u.phone" class="muted small row gap-8"><Icon name="phone" :size="14" /> {{ u.phone }}</div>

        <div class="ustats">
          <template v-if="u.roles.includes('worker')">
            <div><div class="muted small">Проектов</div><b>{{ u.projects_count }}</b></div>
            <div><div class="muted small">Заработал</div><b class="mono">{{ money(u.total_earned) }}</b></div>
          </template>
          <div v-if="u.roles.includes('tester')"><div class="muted small">Проверил проектов</div><b>{{ u.reviewed_count }}</b></div>
          <div v-if="u.roles.includes('admin')" class="full muted small">Полный доступ: проекты, финансы, серверы, пользователи.</div>
        </div>
      </div>
    </transition-group>

    <div v-if="!filtered.length" class="card center muted" style="padding: 50px">{{ byRoleTab.length ? 'Никого не найдено' : 'Здесь пока никого нет' }}</div>

    <!-- ===== Создание / редактирование ===== -->
    <Modal v-model="show" :eyebrow="editing ? 'Редактирование' : 'Новый пользователь'" :title="editing ? (editing.full_name || editing.username) : 'Создать пользователя'">
      <div class="field">
        <label>Роли — можно отметить несколько</label>
        <div class="role-pick">
          <label v-for="r in roles" :key="r.v" class="role-opt" :class="{ on: form.roles.includes(r.v), locked: lockedRole(r.v) }"
            :title="lockedRole(r.v) || ''">
            <input type="checkbox" :value="r.v" v-model="form.roles" :disabled="!!lockedRole(r.v)" />
            <span class="box"><svg width="13" height="13" viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
            <span class="role-txt">
              <b class="row gap-8"><Icon :name="r.icon" :size="15" /> {{ r.label }}</b>
              <span class="muted small">{{ r.hint }}</span>
            </span>
          </label>
        </div>
        <span v-if="!form.roles.length" class="small" style="color: var(--bad-fg)">Отметьте хотя бы одну роль.</span>
      </div>

      <div class="grid-2">
        <div class="field"><label>ФИО *</label><input v-model="form.full_name" class="input" placeholder="Айдос Серіков" /></div>
        <div class="field"><label>Логин *</label><input v-model="form.username" class="input" placeholder="aidos" autocomplete="off" /></div>
      </div>
      <div class="grid-2">
        <div class="field"><label>Телефон</label><input v-model="form.phone" class="input" placeholder="+7 700 000 00 00" /></div>
        <div class="field">
          <label>{{ editing ? 'Новый пароль' : 'Пароль *' }}</label>
          <input v-model="form.password" class="input" :placeholder="editing ? 'оставьте пустым' : 'минимум 6 символов'" autocomplete="new-password" />
        </div>
      </div>


      <transition name="pop"><div v-if="error" class="badge red" style="margin-top: 8px">{{ error }}</div></transition>
      <div class="row between mt-16">
        <button class="btn ghost" @click="show = false">Отмена</button>
        <button class="btn primary" :disabled="busy || !valid" @click="save">
          <span v-if="busy" class="spinner"></span><span v-else>Сохранить</span>
        </button>
      </div>
    </Modal>

    <!-- ===== Удаление ===== -->
    <Modal v-model="delModal" eyebrow="Удаление" title="Удалить пользователя?">
      <p class="muted">
        <b style="color: var(--text)">{{ delTarget?.full_name || delTarget?.username }}</b>
({{ delTarget?.roles_display }}) больше не сможет войти в систему. Отменить удаление нельзя.
      </p>
      <transition name="pop"><div v-if="delError" class="badge red" style="margin-top: 8px">{{ delError }}</div></transition>
      <div class="row between mt-16">
        <button class="btn ghost" @click="delModal = false">Не удалять</button>
        <button class="btn danger" :disabled="busy" @click="confirmDelete">
          <span v-if="busy" class="spinner"></span><span v-else>Удалить</span>
        </button>
      </div>
    </Modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api, { money } from '../../api'
import { useAuth } from '../../stores/auth'
import Modal from '../../components/Modal.vue'
import Icon from '../../components/Icon.vue'
import FilterBar from '../../components/FilterBar.vue'
import { textMatch } from '../../filters'

const emit = defineEmits(['changed'])
const auth = useAuth()
const users = ref([])
const filter = ref('all')

const roles = [
  { v: 'worker', label: 'Рабочий', icon: 'user', hint: 'Видит свои проекты и заработок, отправляет работу на проверку.' },
  { v: 'tester', label: 'Тестировщик', icon: 'check-circle', hint: 'Видит все проекты и проверяет любой: принимает или возвращает с замечаниями. Денег не видит.' },
  { v: 'admin', label: 'Админ', icon: 'shield', hint: 'Полный доступ ко всему, включая финансы и пользователей.' },
]
const roleCls = { admin: 'amber', worker: 'blue', tester: 'green' }
const roleLabel = { admin: 'Админ', worker: 'Рабочий', tester: 'Тестировщик' }

const byRole = (role) => users.value.filter(u => u.roles.includes(role))
const workers = computed(() => byRole('worker'))
const testers = computed(() => byRole('tester'))
const filters = computed(() => [
  { v: 'all', label: 'Все', count: users.value.length },
  { v: 'worker', label: 'Рабочие', count: workers.value.length },
  { v: 'tester', label: 'Тестировщики', count: testers.value.length },
  { v: 'admin', label: 'Админы', count: byRole('admin').length },
])
const byRoleTab = computed(() => (filter.value === 'all' ? users.value : byRole(filter.value)))
const q = ref('')
const filtered = computed(() => byRoleTab.value.filter(u =>
  textMatch(q.value, u.full_name, u.username, u.phone, u.roles_display)))

// какую роль снять нельзя (сервер всё равно проверит): свою админскую и «Рабочего» при проектах
function lockedRole(r) {
  const u = editing.value
  if (!u || !u.roles.includes(r)) return ''
  if (r === 'admin' && u.id === auth.user?.id) return 'Роль админа с себя снять нельзя'
  if (r === 'worker' && u.projects_count > 0) return 'За рабочим есть проекты — роль снять нельзя'
  return ''
}

function initials(u) { const n = u.full_name || u.username; return n.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase() }

const show = ref(false)
const busy = ref(false)
const error = ref('')
const editing = ref(null)
const blank = () => ({ roles: ['worker'], full_name: '', username: '', phone: '', password: '' })
const form = reactive(blank())

const valid = computed(() =>
  form.roles.length && form.username.trim() && form.full_name.trim() && (editing.value ? (!form.password || form.password.length >= 6) : form.password.length >= 6))

function openCreate() {
  editing.value = null
  Object.assign(form, blank(), { roles: [filter.value === 'all' ? 'worker' : filter.value] })
  error.value = ''; show.value = true
}
function openEdit(u) {
  editing.value = u
  Object.assign(form, { roles: [...u.roles], full_name: u.full_name, username: u.username, phone: u.phone, password: '' })
  error.value = ''; show.value = true
}

async function save() {
  busy.value = true; error.value = ''
  try {
    const body = { full_name: form.full_name.trim(), username: form.username.trim(), phone: form.phone.trim(), roles: form.roles }
    if (form.password) body.password = form.password
    if (editing.value) await api.patch(`/users/${editing.value.id}/`, body)
    else await api.post('/users/', body)
    show.value = false
    await load(); emit('changed')
  } catch (e) {
    const d = e.response?.data || {}
    error.value = d.detail || d.username?.[0] || d.password?.[0] || 'Проверьте поля (логин должен быть уникальным)'
  } finally { busy.value = false }
}

const delModal = ref(false)
const delTarget = ref(null)
const delError = ref('')
function askDelete(u) { delTarget.value = u; delError.value = ''; delModal.value = true }
async function confirmDelete() {
  busy.value = true; delError.value = ''
  try {
    await api.delete(`/users/${delTarget.value.id}/`)
    delModal.value = false
    await load(); emit('changed')
  } catch (e) {
    delError.value = e.response?.data?.detail || 'Не удалось удалить'
  } finally { busy.value = false }
}

async function load() { users.value = (await api.get('/users/')).data }
onMounted(load)
</script>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; position: relative; }
.ucard { display: flex; flex-direction: column; gap: 6px; transition: transform .2s, border-color .2s; }
.ucard:hover { transform: translateY(-3px); border-color: var(--stroke-strong); }
.avatar { width: 52px; height: 52px; border-radius: 15px; display: grid; place-items: center; font-weight: 800; font-size: 18px; background: var(--grad-brand); color: white; }
.avatar.tester { background: linear-gradient(135deg, #059669, #047857); }
.avatar.admin { background: linear-gradient(135deg, #d97706, #b45309); }
.uname { margin: 8px 0 0; font-size: 18px; font-weight: 700; }
.count { opacity: .7; font-weight: 700; margin-left: 2px; }
.ustats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--stroke); }
.ustats .full { grid-column: 1 / -1; }

.role-pick { display: flex; flex-direction: column; gap: 8px; }
.role-opt { display: flex; align-items: flex-start; gap: 12px; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--stroke); background: var(--input-bg); cursor: pointer; transition: border-color .2s, background .2s; }
.role-opt:hover { border-color: var(--stroke-strong); }
.role-opt.on { border-color: var(--brand); background: var(--info-bg); }
.role-opt.locked { cursor: not-allowed; opacity: .75; }
.role-opt input { display: none; }
.role-opt .box { margin-top: 2px; width: 20px; height: 20px; border-radius: 6px; border: 2px solid var(--stroke-strong); display: grid; place-items: center; flex-shrink: 0; transition: all .2s; }
.role-opt.on .box { background: var(--brand); border-color: var(--brand); }
.role-opt .box svg { opacity: 0; transform: scale(.5); transition: all .2s; }
.role-opt.on .box svg { opacity: 1; transform: scale(1); }
.role-txt { display: flex; flex-direction: column; gap: 2px; }

</style>
