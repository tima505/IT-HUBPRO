// Общие помощники для поиска и фильтра по датам на страницах со списками.

const norm = (s) => String(s ?? '').toLowerCase().replace(/ё/g, 'е').trim()

/** Каждое слово запроса должно найтись хотя бы в одном из полей. */
export function textMatch(query, ...fields) {
  const words = norm(query).split(/\s+/).filter(Boolean)
  if (!words.length) return true
  const hay = fields.map(norm).join(' ')
  return words.every(w => hay.includes(w))
}

/** Дата (YYYY-MM-DD или ISO с временем) попадает в период [from, to]; пустые границы не ограничивают. */
export function inRange(date, from, to) {
  if (!from && !to) return true
  if (!date) return false
  const d = String(date).slice(0, 10)
  return (!from || d >= from) && (!to || d <= to)
}

const iso = (d) => {
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Быстрые периоды для фильтра дат. */
export const PERIODS = [
  { v: '', label: 'За всё время' },
  { v: 'week', label: 'Последние 7 дней' },
  { v: 'month', label: 'Этот месяц' },
  { v: 'prev', label: 'Прошлый месяц' },
  { v: 'quarter', label: 'Последние 3 месяца' },
  { v: 'year', label: 'Этот год' },
  { v: 'custom', label: 'Свой период…' },
]

export function periodRange(v) {
  const now = new Date()
  const y = now.getFullYear(), m = now.getMonth()
  switch (v) {
    case 'week': return [iso(new Date(y, m, now.getDate() - 6)), iso(now)]
    case 'month': return [iso(new Date(y, m, 1)), iso(new Date(y, m + 1, 0))]
    case 'prev': return [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))]
    case 'quarter': return [iso(new Date(y, m - 2, 1)), iso(new Date(y, m + 1, 0))]
    case 'year': return [`${y}-01-01`, `${y}-12-31`]
    default: return ['', '']
  }
}
