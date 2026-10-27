"""
Сервисы: балансы фондов, долги, история, уведомления, отчёт по задачам.
"""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count as models_count, Sum
from django.utils import timezone

from .models import (
    Bucket, Expense, ExpenseCategory, Notification, Payer, Payment, PaymentKind, PlanItem, PlanPeriod, Project, ProjectStatus,
    Server, ServerRenewal, ServerStatus, SubTask, Task, TaskStatus, User, WorkerPayout, week_start,
)


def _sum(qs, field) -> Decimal:
    return qs.aggregate(s=Sum(field))['s'] or Decimal('0')


def fund_balances() -> dict:
    """Текущие остатки трёх «корзин» денег.

    Приход: распределение платежей. Расход: серверы (если платит компания), выплаты рабочим
    и расходы компании — из выбранной корзины.
    """
    payments = Payment.objects.all()
    income = {
        Bucket.FUND20: _sum(payments, 'fund20_amount'),
        Bucket.FUND5: _sum(payments, 'fund5_amount'),
        Bucket.COMPANY: _sum(payments, 'company_amount'),
    }

    expense = {Bucket.FUND20: Decimal('0'), Bucket.FUND5: Decimal('0'), Bucket.COMPANY: Decimal('0')}
    sources = (
        Server.objects.filter(paid_by=Payer.COMPANY),          # сервер, оплаченный клиентом, — не наш расход
        ServerRenewal.objects.filter(paid_by=Payer.COMPANY),
        WorkerPayout.objects.all(),
        Expense.objects.all(),
    )
    for qs in sources:
        for bucket, total in qs.values_list('paid_from').annotate(t=Sum('amount')):
            expense[bucket] = expense.get(bucket, Decimal('0')) + (total or Decimal('0'))

    result = {}
    for bucket in [Bucket.FUND20, Bucket.FUND5, Bucket.COMPANY]:
        result[bucket] = {
            'income': income[bucket],
            'expense': expense[bucket],
            'balance': income[bucket] - expense[bucket],
        }
    return result


def bucket_balance(bucket: str) -> Decimal:
    """Текущий баланс одной «корзины»."""
    return fund_balances()[bucket]['balance']


def refresh_server_statuses():
    """Истёкшие серверы → «Истёк», продлённые обратно → «Активен»."""
    today = timezone.localdate()
    Server.objects.filter(status=ServerStatus.ACTIVE, expiry_date__lt=today).update(status=ServerStatus.EXPIRED)
    Server.objects.filter(status=ServerStatus.EXPIRED, expiry_date__gte=today).update(status=ServerStatus.ACTIVE)


def finance_summary() -> dict:
    balances = fund_balances()
    payments = Payment.objects.all()
    debts = debts_summary()
    return {
        'fund20': balances[Bucket.FUND20],
        'fund5': balances[Bucket.FUND5],
        'company': balances[Bucket.COMPANY],
        'total_income': _sum(payments, 'amount'),
        'worker_payouts': _sum(WorkerPayout.objects.all(), 'amount'),
        'clients_debt': debts['clients_total'],
        'workers_debt': debts['workers_total'],
        'server_expense': (
            _sum(Server.objects.filter(paid_by=Payer.COMPANY), 'amount')
            + _sum(ServerRenewal.objects.filter(paid_by=Payer.COMPANY), 'amount')
        ),
        'other_expense': _sum(Expense.objects.all(), 'amount'),
    }


def worker_earnings(worker: User) -> Decimal:
    """Сколько всего выплачено рабочему (по всем его проектам)."""
    return _sum(WorkerPayout.objects.filter(worker=worker), 'amount')


def debts_summary() -> dict:
    """Кто сколько должен.

    clients — клиенты с непогашенным долгом (проекты одного клиента объединяются
              по имени + телефону), workers — сколько компания должна рабочим.
    """
    projects = (Project.objects.exclude(status=ProjectStatus.CANCELLED)
                .select_related('worker').prefetch_related('payments', 'payouts'))
    clients, workers = {}, {}
    for pr in projects:
        if pr.debt > 0:
            name = pr.client_name.strip() or 'Клиент не указан'
            key = (name.lower(), pr.client_phone.strip())
            c = clients.setdefault(key, {'client_name': name, 'client_phone': pr.client_phone.strip(),
                                         'debt': Decimal('0'), 'price': Decimal('0'), 'paid': Decimal('0'),
                                         'projects': []})
            c['debt'] += pr.debt
            c['price'] += pr.price
            c['paid'] += pr.paid
            c['projects'].append(_debt_project(pr, pr.debt))
        if pr.worker_debt > 0:
            w = workers.setdefault(pr.worker_id, {'worker_id': pr.worker_id, 'worker_name': str(pr.worker),
                                                  'debt': Decimal('0'), 'projects': []})
            w['debt'] += pr.worker_debt
            w['projects'].append({**_debt_project(pr, pr.worker_debt),
                                  'owed': pr.worker_amount, 'paid': pr.worker_paid})
    clients = sorted(clients.values(), key=lambda c: -c['debt'])
    workers = sorted(workers.values(), key=lambda w: -w['debt'])
    return {
        'clients': clients,
        'workers': workers,
        'clients_total': sum((c['debt'] for c in clients), Decimal('0')),
        'workers_total': sum((w['debt'] for w in workers), Decimal('0')),
    }


def _debt_project(pr, debt):
    last = max((p.date for p in pr.payments.all() if p.kind != PaymentKind.MONTHLY), default=None)
    return {'id': pr.id, 'name': pr.name, 'status': pr.status, 'price': pr.price, 'paid': pr.paid,
            'debt': debt, 'last_payment': last, 'deadline_date': pr.deadline_date}


BUCKET_FIELD = {
    Bucket.COMPANY: 'company_amount',
    Bucket.FUND20: 'fund20_amount',
    Bucket.FUND5: 'fund5_amount',
}


def finance_breakdown(bucket: str) -> dict:
    """Откуда пришли и на что ушли деньги конкретной «корзины».

    income  — доли поступлений по проектам, попавшие в эту корзину.
    expense — оплата серверов (покупка/продление) из этой корзины.
    """
    field = BUCKET_FIELD.get(bucket)
    if not field:
        return {'bucket': bucket, 'income': [], 'expense': [],
                'income_total': Decimal('0'), 'expense_total': Decimal('0')}

    income = []
    for p in Payment.objects.select_related('project').all():
        amt = getattr(p, field)
        if amt and amt > 0:
            income.append({
                'source': p.project.name,
                'detail': p.get_kind_display(),
                'date': p.date,
                'base_amount': p.amount,
                'amount': amt,
            })

    expense = []
    for s in Server.objects.filter(paid_from=bucket, paid_by=Payer.COMPANY):
        expense.append({'source': f'Сервер «{s.label}»', 'detail': 'Покупка',
                        'date': s.purchase_date, 'amount': s.amount})
    for rn in ServerRenewal.objects.filter(paid_from=bucket, paid_by=Payer.COMPANY).select_related('server'):
        expense.append({'source': f'Сервер «{rn.server.label}»', 'detail': 'Продление',
                        'date': rn.date, 'amount': rn.amount})
    for po in WorkerPayout.objects.filter(paid_from=bucket).select_related('worker', 'project'):
        expense.append({'source': f'Рабочему {po.worker}', 'detail': f'Выплата по «{po.project.name}»',
                        'date': po.date, 'amount': po.amount})
    for ex in Expense.objects.filter(paid_from=bucket):
        expense.append({'source': ex.title, 'detail': ex.get_category_display(),
                        'date': ex.date, 'amount': ex.amount})

    income.sort(key=lambda x: x['date'], reverse=True)
    expense.sort(key=lambda x: x['date'], reverse=True)
    return {
        'bucket': bucket,
        'income': income,
        'expense': expense,
        'income_total': sum((x['amount'] for x in income), Decimal('0')),
        'expense_total': sum((x['amount'] for x in expense), Decimal('0')),
    }


# --------------------------------------------------------------------------- #
#  История: единая лента всего, что происходило
# --------------------------------------------------------------------------- #
def activity_log() -> list:
    """События по проектам, деньгам, серверам и проверке — новые сверху.

    date — дата события для показа и фильтра, at — точное время для сортировки.
    """
    from .models import ProjectComment  # локально, чтобы не плодить импорт сверху
    events = []

    def add(key, kind, date, at, title, text='', amount=None, project=None, who=''):
        events.append({
            'id': key, 'type': kind, 'date': date, 'at': at, 'title': title, 'text': text,
            'amount': amount, 'who': who,
            'project_id': project.id if project else None,
            'project_name': project.name if project else '',
        })

    for p in Project.objects.select_related('worker'):
        add(f'project-{p.id}', 'project', timezone.localtime(p.created_at).date(), p.created_at,
            'Создан проект', f'Рабочий: {p.worker}', p.total_price or None, p, '')
        if p.finished_date and p.review_status == 'none':  # сдача отмечена админом без проверки
            add(f'finish-{p.id}', 'project', p.finished_date, p.created_at,
                'Рабочий отметил сдачу', '', None, p, str(p.worker))

    for pay in Payment.objects.select_related('project'):
        add(f'pay-{pay.id}', 'payment', pay.date, pay.created_at,
            f'Платёж: {pay.get_kind_display()}',
            (f'{pay.note} · ' if pay.note else '') +
            f'фонды {pay.fund20_amount + pay.fund5_amount:,.0f} · компании {pay.company_amount:,.0f} ₸'.replace(',', ' '),
            pay.amount, pay.project)

    for po in WorkerPayout.objects.select_related('project', 'worker'):
        add(f'payout-{po.id}', 'payout', po.date, po.created_at,
            f'Выплата рабочему: {po.worker}',
            (f'{po.note} · ' if po.note else '') + f'из «{po.get_paid_from_display()}»',
            po.amount, po.project)

    def payer_text(obj):
        if obj.paid_by == Payer.CLIENT:
            return f'оплатил клиент: {obj.amount:,.0f} ₸'.replace(',', ' ')
        return f'оплачен из: {obj.get_paid_from_display()}'

    for s in Server.objects.select_related('project'):
        add(f'server-{s.id}', 'server', s.purchase_date, s.created_at,
            f'Куплен сервер «{s.label}»', f'на {term_text(s.months, s.days)}, {payer_text(s)}',
            s.amount if s.paid_by == Payer.COMPANY else None, s.project)

    for rn in ServerRenewal.objects.select_related('server__project'):
        add(f'renew-{rn.id}', 'server', rn.date, rn.created_at,
            f'Продлён сервер «{rn.server.label}»',
            f'на {term_text(rn.months, rn.days)}, до {rn.new_expiry:%d.%m.%Y}, {payer_text(rn)}',
            rn.amount if rn.paid_by == Payer.COMPANY else None, rn.server.project)

    for ex in Expense.objects.select_related('project', 'created_by'):
        add(f'expense-{ex.id}', 'expense', ex.date, ex.created_at,
            f'Расход: {ex.title}', f'{ex.get_category_display()} · из «{ex.get_paid_from_display()}»'
            + (f' · {ex.note}' if ex.note else ''),
            ex.amount, ex.project, str(ex.created_by) if ex.created_by_id else '')

    for c in ProjectComment.objects.select_related('project', 'author'):
        add(f'comment-{c.id}', 'comment' if c.kind == ProjectComment.Kind.COMMENT else 'review',
            timezone.localtime(c.created_at).date(), c.created_at,
            c.get_kind_display(), c.text, None, c.project, str(c.author) if c.author_id else '')

    events.sort(key=lambda e: (e['date'], e['at']), reverse=True)
    return events


# --------------------------------------------------------------------------- #
#  Уведомления
# --------------------------------------------------------------------------- #

SERVER_MILESTONES = [7, 1]     # за сколько дней до конца сервера напоминать
PROJECT_MILESTONES = [3, 0]    # за сколько дней до ежемесячной оплаты напоминать
TASK_MILESTONES = [1, 0]       # за сколько дней до дедлайна задачи напоминать исполнителю


def _admins():
    return User.with_role(User.Role.ADMIN).filter(is_active=True)


def _testers():
    return User.with_role(User.Role.TESTER).filter(is_active=True)


def _create(recipient, kind, title, message, dedup_key):
    Notification.objects.get_or_create(
        dedup_key=dedup_key,
        defaults=dict(recipient=recipient, kind=kind, title=title, message=message),
    )


def notify_review(comment, recipients, title, message):
    """Уведомление о шаге проверки/комментарии — всем получателям, кроме автора."""
    seen = set()
    for user in recipients:
        if user is None or user.id == comment.author_id or user.id in seen:
            continue
        seen.add(user.id)
        _create(user, Notification.Kind.REVIEW, title, message,
                f'review:{comment.project_id}:{comment.id}:{user.id}')


def _current_milestone(left: int, milestones):
    """Веха, в которую сейчас попадает срок.

    Срабатывает, даже если в сам день вехи никто не открывал колокольчик:
    при left=5 и вехах [7, 1] → 7. Просрочка → 'overdue'. Раньше первой вехи → None.
    """
    if left < 0:
        return 'overdue'
    passed = [m for m in milestones if left <= m]
    return min(passed) if passed else None


def _days(n: int) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return f'{n} день'
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f'{n} дня'
    return f'{n} дней'


def _tenge(amount) -> str:
    return f'{amount:,.0f} ₸'.replace(',', ' ')


def notify_task_assigned(task, by_user):
    """Уведомить исполнителя о новой задаче, назначенной кем-то другим."""
    if task.assignee_id == getattr(by_user, 'id', None):
        return
    deadline = f' Дедлайн: {task.deadline:%d.%m.%Y}.' if task.deadline else ''
    _create(task.assignee, Notification.Kind.TASK, 'Новая задача',
            f'{by_user} назначил(а) вам задачу «{task.title}».{deadline}',
            f'task:{task.id}:assigned:{task.assignee_id}')


def generate_task_notifications(user):
    """Дедлайны задач пользователя: завтра, сегодня, просрочено."""
    today = timezone.localdate()
    open_tasks = Task.objects.filter(assignee=user, deadline__isnull=False).exclude(status=TaskStatus.DONE)
    for task in open_tasks.filter(deadline__lte=today + timedelta(days=max(TASK_MILESTONES))):
        left = (task.deadline - today).days
        milestone = _current_milestone(left, TASK_MILESTONES)
        if milestone is None:
            continue
        if milestone == 'overdue':
            title, msg = 'Задача просрочена', f'Задача «{task.title}» просрочена на {_days(left)}.'
        elif left == 0:
            title, msg = 'Дедлайн сегодня', f'Сегодня дедлайн задачи «{task.title}».'
        else:
            title, msg = 'Дедлайн завтра', f'Завтра дедлайн задачи «{task.title}».'
        _create(user, Notification.Kind.TASK, title, msg, f'task:{task.id}:{task.deadline}:{milestone}:{user.id}')


def generate_notifications():
    """Создаёт уведомления по достигнутым вехам (без дублей).

    Вызывается при опросе колокольчика фронтендом.
    """
    refresh_server_statuses()
    today = timezone.localdate()
    admins = list(_admins())
    if not admins:
        return

    # --- серверы: за 7 и за 1 день до окончания, плюс просрочка ---
    for server in Server.objects.all():
        left = (server.expiry_date - today).days
        milestone = _current_milestone(left, SERVER_MILESTONES)
        if milestone is None:
            continue
        key = f'server:{server.id}:{server.expiry_date}:{milestone}'
        until = f'{server.expiry_date:%d.%m.%Y}'
        if milestone == 'overdue':
            title = 'Сервер истёк'
            msg = f'Срок сервера «{server.label}» истёк {until} — просрочка {_days(left)}.'
        elif left == 0:
            title = 'Продление сервера'
            msg = f'Сегодня последний день сервера «{server.label}» (до {until}).'
        else:
            title = 'Продление сервера'
            msg = f'Осталось {_days(left)} до продления сервера «{server.label}» (до {until}).'
        for admin in admins:
            _create(admin, Notification.Kind.SERVER, title, msg, f'{key}:{admin.id}')

    # --- ежемесячные проекты: за 3 дня, в последний день, плюс просрочка ---
    monthly = Project.objects.filter(has_monthly=True, status=ProjectStatus.ACTIVE)
    for project in monthly:
        due = project.monthly_next_due
        if not due:
            continue
        left = (due - today).days
        milestone = _current_milestone(left, PROJECT_MILESTONES)
        if milestone is None:
            continue
        key = f'project:{project.id}:{due}:{milestone}'
        amount = _tenge(project.monthly_amount or Decimal('0'))
        if milestone == 'overdue':
            title = 'Просрочена оплата проекта'
            msg = (f'Оплата продления проекта «{project.name}» просрочена на {_days(left)} '
                   f'(срок {due:%d.%m.%Y}). Клиент должен оплатить {amount}.')
        elif left == 0:
            title = 'Продление проекта'
            msg = (f'Сегодня последний день оплаты продления проекта «{project.name}». '
                   f'Клиент должен оплатить {amount}.')
        else:
            title = 'Продление проекта'
            msg = (f'Осталось {_days(left)} до оплаты продления проекта «{project.name}». '
                   f'Сумма к оплате: {amount}.')
        for admin in admins:
            _create(admin, Notification.Kind.PROJECT, title, msg, f'{key}:{admin.id}')


# --------------------------------------------------------------------------- #
#  Аналитика задач за месяц
# --------------------------------------------------------------------------- #
def month_bounds(year: int, month: int):
    first = date(year, month, 1)
    return first, date(year, month, calendar.monthrange(year, month)[1])


def _person(user):
    return {'id': user.id, 'name': str(user), 'username': user.username, 'roles': user.roles}


def task_report(year: int, month: int, users) -> dict:
    """Кто сколько задач сделал за месяц.

    done      — задачи, переведённые в «Готово» в этом месяце;
    on_time   — из них выполненные не позже дедлайна (или без дедлайна);
    late      — выполненные после дедлайна;
    overdue   — дедлайн в этом месяце уже прошёл, а задача не выполнена;
    in_work   — открытые задачи сейчас (снимок на сегодня);
    subtasks  — подзадачи, отмеченные выполненными в этом месяце.
    """
    first, last = month_bounds(year, month)
    today = timezone.localdate()
    users = list(users)
    ids = [u.id for u in users]

    done_tasks = list(
        Task.objects.filter(assignee_id__in=ids, status=TaskStatus.DONE,
                            completed_at__date__gte=first, completed_at__date__lte=last)
        .select_related('project', 'assignee').order_by('completed_at'))
    overdue_tasks = list(
        Task.objects.filter(assignee_id__in=ids, deadline__gte=first, deadline__lte=last,
                            deadline__lt=today).exclude(status=TaskStatus.DONE)
        .select_related('project', 'assignee').order_by('deadline'))
    in_work = {}
    for row in (Task.objects.filter(assignee_id__in=ids).exclude(status=TaskStatus.DONE)
                .values('assignee_id').annotate(n=models_count('id'))):
        in_work[row['assignee_id']] = row['n']
    subtasks = {}
    for row in (SubTask.objects.filter(task__assignee_id__in=ids, is_done=True,
                                       done_at__date__gte=first, done_at__date__lte=last)
                .values('task__assignee_id').annotate(n=models_count('id'))):
        subtasks[row['task__assignee_id']] = row['n']

    def task_row(t):
        return {'id': t.id, 'title': t.title, 'project': t.project.name if t.project else None,
                'deadline': t.deadline, 'completed': t.completed_date, 'state': t.deadline_state()}

    people = []
    for u in users:
        mine = [t for t in done_tasks if t.assignee_id == u.id]
        late = [t for t in mine if t.deadline_state() == 'late']
        overdue = [t for t in overdue_tasks if t.assignee_id == u.id]
        durations = [(t.completed_at - t.created_at).total_seconds() / 86400 for t in mine]
        people.append({
            **_person(u),
            'done': len(mine),
            'on_time': len(mine) - len(late),
            'late': len(late),
            'overdue': len(overdue),
            'in_work': in_work.get(u.id, 0),
            'subtasks_done': subtasks.get(u.id, 0),
            'on_time_rate': round((len(mine) - len(late)) * 100 / len(mine)) if mine else None,
            'avg_days': round(sum(durations) / len(durations), 1) if durations else None,
            'done_tasks': [task_row(t) for t in mine],
            'overdue_tasks': [task_row(t) for t in overdue],
        })
    people.sort(key=lambda p: (-p['done'], p['late'] + p['overdue'], p['name']))

    by_day = {first + timedelta(days=i): 0 for i in range((last - first).days + 1)}
    for t in done_tasks:
        by_day[t.completed_date] += 1

    done = len(done_tasks)
    late = sum(p['late'] for p in people)
    return {
        'month': f'{year:04d}-{month:02d}',
        'first': first, 'last': last,
        'totals': {
            'done': done,
            'on_time': done - late,
            'late': late,
            'overdue': sum(p['overdue'] for p in people),
            'in_work': sum(p['in_work'] for p in people),
            'subtasks_done': sum(p['subtasks_done'] for p in people),
            'on_time_rate': round((done - late) * 100 / done) if done else None,
        },
        'by_day': [{'date': d, 'done': n} for d, n in by_day.items()],
        'people': people,
    }


# --------------------------------------------------------------------------- #
#  Личный план: статистика
# --------------------------------------------------------------------------- #
def _rate(done, planned):
    return round(done * 100 / planned) if planned else None


def _plan_counts(items):
    """{дата: [запланировано, выполнено]} — перенесённые считаются невыполненными."""
    counts = {}
    for it in items:
        c = counts.setdefault(it.date, [0, 0])
        c[0] += 1
        c[1] += 1 if it.is_done else 0
    return counts


def plan_stats(user, days: int = 14, weeks: int = 8) -> dict:
    """Выполнение личного плана: по дням, по неделям, серия дней с полностью выполненным планом."""
    today = timezone.localdate()
    first_day = today - timedelta(days=days - 1)
    this_week = week_start(today)
    first_week = this_week - timedelta(weeks=weeks - 1)

    day_items = list(PlanItem.objects.filter(user=user, period=PlanPeriod.DAY, date__gte=first_day - timedelta(days=60), date__lte=today))
    week_items = list(PlanItem.objects.filter(user=user, period=PlanPeriod.WEEK, date__gte=first_week, date__lte=this_week))
    by_day = _plan_counts(day_items)
    by_week = _plan_counts(week_items)
    # для недели учитываем и дневные пункты внутри неё
    week_with_days = {}
    for d, (planned, done) in by_day.items():
        w = week_with_days.setdefault(week_start(d), [0, 0])
        w[0] += planned
        w[1] += done

    day_rows = []
    for i in range(days):
        d = first_day + timedelta(days=i)
        planned, done = by_day.get(d, (0, 0))
        day_rows.append({'date': d, 'planned': planned, 'done': done, 'rate': _rate(done, planned)})

    week_rows = []
    for i in range(weeks):
        w = first_week + timedelta(weeks=i)
        wp, wd = by_week.get(w, (0, 0))
        dp, dd = week_with_days.get(w, (0, 0))
        week_rows.append({'week': w, 'week_end': w + timedelta(days=6),
                          'week_planned': wp, 'week_done': wd,
                          'planned': wp + dp, 'done': wd + dd, 'rate': _rate(wd + dd, wp + dp)})

    # серия: подряд идущие дни (назад от вчера, плюс сегодня, если план уже закрыт),
    # в которые план был и выполнен полностью
    streak, d = 0, today
    planned, done = by_day.get(d, (0, 0))
    if not (planned and done == planned):
        d -= timedelta(days=1)
    while True:
        planned, done = by_day.get(d, (0, 0))
        if not planned or done < planned:
            break
        streak += 1
        d -= timedelta(days=1)

    period_planned = sum(r['planned'] for r in day_rows)
    period_done = sum(r['done'] for r in day_rows)
    active_days = [r for r in day_rows if r['planned']]
    return {
        'today': today,
        'days': day_rows,
        'weeks': week_rows,
        'streak': streak,
        'summary': {
            'planned': period_planned,
            'done': period_done,
            'rate': _rate(period_done, period_planned),
            'days_with_plan': len(active_days),
            'perfect_days': sum(1 for r in active_days if r['done'] == r['planned']),
        },
    }


def team_plans() -> list:
    """Сводка по команде за текущую неделю (для админа)."""
    today = timezone.localdate()
    monday = week_start(today)
    users = list(User.objects.filter(is_active=True).order_by('full_name', 'username'))
    items = list(PlanItem.objects.filter(date__gte=monday, date__lte=monday + timedelta(days=6)))
    rows = []
    for u in users:
        mine = [it for it in items if it.user_id == u.id]
        today_items = [it for it in mine if it.period == PlanPeriod.DAY and it.date == today]
        planned, done = len(mine), sum(1 for it in mine if it.is_done)
        rows.append({
            'id': u.id, 'name': str(u), 'username': u.username, 'roles': u.roles,
            'week_planned': planned, 'week_done': done, 'week_rate': _rate(done, planned),
            'today_planned': len(today_items), 'today_done': sum(1 for it in today_items if it.is_done),
        })
    rows.sort(key=lambda r: (r['week_planned'] == 0, -(r['week_rate'] or 0), r['name']))
    return rows


# --------------------------------------------------------------------------- #
#  Отчёт по расходам
# --------------------------------------------------------------------------- #
def term_text(months, days) -> str:
    if months:
        if months % 12 == 0:
            years = months // 12
            return '1 год' if years == 1 else f'{years} года' if years < 5 else f'{years} лет'
        return f'{months} мес.'
    return f'{days} дн.'


SERVER_CATEGORY = ('servers', 'Серверы')
PAYOUT_CATEGORY = ('payouts', 'Выплаты рабочим')


def expense_report(first, last) -> dict:
    """Все расходы компании за период: ручные расходы, серверы, продления, выплаты рабочим.

    Серверы, которые оплатил клиент, в итоги не входят — они в отдельном списке client_paid.
    """
    rows, client_paid = [], []

    def row(kind, ident, date, amount, category, title, bucket, bucket_label, project=None, note=''):
        return {'id': f'{kind}-{ident}', 'kind': kind, 'date': date, 'amount': amount,
                'category': category[0], 'category_display': category[1], 'title': title,
                'paid_from': bucket, 'paid_from_display': bucket_label, 'note': note,
                'project_id': project.id if project else None, 'project_name': project.name if project else ''}

    in_period = dict(date__gte=first, date__lte=last)
    for ex in Expense.objects.filter(**in_period).select_related('project'):
        rows.append(row('expense', ex.id, ex.date, ex.amount, (ex.category, ex.get_category_display()),
                        ex.title, ex.paid_from, ex.get_paid_from_display(), ex.project, ex.note))
    for s in Server.objects.filter(purchase_date__gte=first, purchase_date__lte=last).select_related('project'):
        r = row('server', s.id, s.purchase_date, s.amount, SERVER_CATEGORY, f'Покупка сервера «{s.label}»',
                s.paid_from, s.get_paid_from_display(), s.project, f'на {term_text(s.months, s.days)}')
        (client_paid if s.paid_by == Payer.CLIENT else rows).append(r)
    for rn in ServerRenewal.objects.filter(**in_period).select_related('server__project'):
        r = row('renewal', rn.id, rn.date, rn.amount, SERVER_CATEGORY, f'Продление сервера «{rn.server.label}»',
                rn.paid_from, rn.get_paid_from_display(), rn.server.project, f'на {term_text(rn.months, rn.days)}')
        (client_paid if rn.paid_by == Payer.CLIENT else rows).append(r)
    for po in WorkerPayout.objects.filter(**in_period).select_related('worker', 'project'):
        rows.append(row('payout', po.id, po.date, po.amount, PAYOUT_CATEGORY, f'Выплата: {po.worker}',
                        po.paid_from, po.get_paid_from_display(), po.project, po.note))

    rows.sort(key=lambda r: (r['date'], r['id']), reverse=True)
    client_paid.sort(key=lambda r: r['date'], reverse=True)
    total = sum((r['amount'] for r in rows), Decimal('0'))

    def group(key, label_key):
        out = {}
        for r in rows:
            g = out.setdefault(r[key], {'key': r[key], 'label': r[label_key], 'amount': Decimal('0'), 'count': 0})
            g['amount'] += r['amount']
            g['count'] += 1
        return sorted(out.values(), key=lambda g: -g['amount'])

    by_month = {}
    for r in rows:
        k = f"{r['date']:%Y-%m}"
        by_month[k] = by_month.get(k, Decimal('0')) + r['amount']
    months, d = [], first.replace(day=1)
    while d <= last:
        k = f'{d:%Y-%m}'
        months.append({'month': k, 'amount': by_month.get(k, Decimal('0'))})
        d = add_months_simple(d)

    return {
        'from': first, 'to': last,
        'total': total, 'count': len(rows),
        'by_category': group('category', 'category_display'),
        'by_fund': group('paid_from', 'paid_from_display'),
        'by_month': months,
        'rows': rows,
        'client_paid': client_paid,
        'client_paid_total': sum((r['amount'] for r in client_paid), Decimal('0')),
    }


def add_months_simple(d):
    """Первое число следующего месяца."""
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)
