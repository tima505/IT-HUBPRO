"""
Сервисы: расчёт балансов фондов и генерация уведомлений.
"""
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import (
    Bucket, Notification, Payment, Project, ProjectStatus,
    Server, ServerRenewal, ServerStatus, User, add_months,
)


def _sum(qs, field) -> Decimal:
    return qs.aggregate(s=Sum(field))['s'] or Decimal('0')


def fund_balances() -> dict:
    """Текущие остатки трёх «корзин» денег.

    Приход: распределение платежей. Расход: оплата серверов из выбранной корзины.
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

    result = {}
    for bucket in [Bucket.FUND20, Bucket.FUND5, Bucket.COMPANY]:
        result[bucket] = {
            'income': income[bucket],
            'expense': expense[bucket],
            'balance': income[bucket] - expense[bucket],
        }
    return result


def finance_summary() -> dict:
    balances = fund_balances()
    payments = Payment.objects.all()
    return {
        'fund20': balances[Bucket.FUND20],
        'fund5': balances[Bucket.FUND5],
        'company': balances[Bucket.COMPANY],
        'total_income': _sum(payments, 'amount'),
        'worker_payouts': _sum(payments, 'worker_amount'),
        'server_expense': (
            _sum(Server.objects.all(), 'amount') + _sum(ServerRenewal.objects.all(), 'amount')
        ),
    }


def worker_earnings(worker: User) -> Decimal:
    """Сколько всего заработал рабочий (по всем его проектам)."""
    return _sum(Payment.objects.filter(project__worker=worker), 'worker_amount')


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
            f'фонды {pay.fund20_amount + pay.fund5_amount:,.0f} · рабочему {pay.worker_amount:,.0f}'
            f' · компании {pay.company_amount:,.0f} ₸'.replace(',', ' '),
            pay.amount, pay.project)

    for s in Server.objects.select_related('project'):
        add(f'server-{s.id}', 'server', s.purchase_date, s.created_at,
            f'Куплен сервер «{s.label}»', f'на {s.days} дн., оплачен из: {s.get_paid_from_display()}',
            s.amount, s.project)

    for rn in ServerRenewal.objects.select_related('server__project'):
        add(f'renew-{rn.id}', 'server', rn.date, rn.created_at,
            f'Продлён сервер «{rn.server.label}»',
            f'на {rn.days} дн., до {rn.new_expiry:%d.%m.%Y}, оплачен из: {rn.get_paid_from_display()}',
            rn.amount, rn.server.project)

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


def generate_notifications():
    """Создаёт уведомления по достигнутым вехам (без дублей).

    Вызывается при опросе колокольчика фронтендом.
    """
    today = timezone.localdate()
    admins = list(_admins())
    if not admins:
        return

    # --- серверы: за 7 и за 1 день до окончания ---
    for server in Server.objects.filter(status=ServerStatus.ACTIVE):
        left = (server.expiry_date - today).days
        for milestone in SERVER_MILESTONES:
            if left == milestone:
                key = f'server:{server.id}:{server.expiry_date}:{milestone}'
                title = 'Продление сервера'
                if milestone == 1:
                    msg = f'Остался 1 день до продления сервера «{server.label}» (до {server.expiry_date:%d.%m.%Y}).'
                else:
                    msg = f'Осталось {milestone} дней до продления сервера «{server.label}» (до {server.expiry_date:%d.%m.%Y}).'
                for admin in admins:
                    _create(admin, Notification.Kind.SERVER, title, msg, f'{key}:{admin.id}')

    # --- ежемесячные проекты: за 3 дня и в последний день ---
    monthly = Project.objects.filter(has_monthly=True, status=ProjectStatus.ACTIVE)
    for project in monthly:
        due = project.monthly_next_due
        if not due:
            continue
        left = (due - today).days
        for milestone in PROJECT_MILESTONES:
            if left == milestone:
                key = f'project:{project.id}:{due}:{milestone}'
                amount = project.monthly_amount or Decimal('0')
                if milestone == 0:
                    msg = (f'Сегодня последний день оплаты продления проекта «{project.name}». '
                           f'Клиент должен оплатить {amount:,.0f} ₸.'.replace(',', ' '))
                else:
                    msg = (f'Осталось {milestone} дня до оплаты продления проекта «{project.name}». '
                           f'Сумма к оплате: {amount:,.0f} ₸.'.replace(',', ' '))
                for admin in admins:
                    _create(admin, Notification.Kind.PROJECT, 'Продление проекта', msg, f'{key}:{admin.id}')
