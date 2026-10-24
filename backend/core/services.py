"""
Сервисы: расчёт балансов фондов и генерация уведомлений.
"""
from decimal import Decimal

from django.db.models import Count as models_count, Sum
from django.utils import timezone

import calendar
from datetime import date, timedelta

from .models import (
    Bucket, Notification, Payment, PaymentKind, Project, ProjectStatus,
    Server, ServerRenewal, ServerStatus, SubTask, Task, TaskStatus, User, WorkerPayout,
)


def _sum(qs, field) -> Decimal:
    return qs.aggregate(s=Sum(field))['s'] or Decimal('0')


def fund_balances() -> dict:
    """Текущие остатки трёх «корзин» денег.

    Приход: распределение платежей. Расход: серверы и выплаты рабочим из выбранной корзины.
    """
    payments = Payment.objects.all()
    income = {
        Bucket.FUND20: _sum(payments, 'fund20_amount'),
        Bucket.FUND5: _sum(payments, 'fund5_amount'),
        Bucket.COMPANY: _sum(payments, 'company_amount'),
    }

    expense = {Bucket.FUND20: Decimal('0'), Bucket.FUND5: Decimal('0'), Bucket.COMPANY: Decimal('0')}
    for bucket, total in Server.objects.values_list('paid_from').annotate(t=Sum('amount')):
        expense[bucket] = expense.get(bucket, Decimal('0')) + (total or Decimal('0'))
    for bucket, total in ServerRenewal.objects.values_list('paid_from').annotate(t=Sum('amount')):
        expense[bucket] = expense.get(bucket, Decimal('0')) + (total or Decimal('0'))
    for bucket, total in WorkerPayout.objects.values_list('paid_from').annotate(t=Sum('amount')):
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
            _sum(Server.objects.all(), 'amount') + _sum(ServerRenewal.objects.all(), 'amount')
        ),
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
    for s in Server.objects.filter(paid_from=bucket):
        expense.append({'source': f'Сервер «{s.label}»', 'detail': 'Покупка',
                        'date': s.purchase_date, 'amount': s.amount})
    for rn in ServerRenewal.objects.filter(paid_from=bucket).select_related('server'):
        expense.append({'source': f'Сервер «{rn.server.label}»', 'detail': 'Продление',
                        'date': rn.date, 'amount': rn.amount})
    for po in WorkerPayout.objects.filter(paid_from=bucket).select_related('worker', 'project'):
        expense.append({'source': f'Рабочему {po.worker}', 'detail': f'Выплата по «{po.project.name}»',
                        'date': po.date, 'amount': po.amount})

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
#  Уведомления
# --------------------------------------------------------------------------- #

SERVER_MILESTONES = [7, 1]     # за сколько дней до конца сервера напоминать
PROJECT_MILESTONES = [3, 0]    # за сколько дней до ежемесячной оплаты напоминать


def _admins():
    return User.objects.filter(role=User.Role.ADMIN)


def _create(recipient, kind, title, message, dedup_key):
    Notification.objects.get_or_create(
        dedup_key=dedup_key,
        defaults=dict(recipient=recipient, kind=kind, title=title, message=message),
    )


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


TASK_MILESTONES = [1, 0]       # за сколько дней до дедлайна задачи напоминать исполнителю


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
    return {'id': user.id, 'name': str(user), 'username': user.username, 'role': user.role}


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
