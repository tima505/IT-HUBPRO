"""
Модели IT HubPro.

Финансовая логика (ключевое):
  У проекта одна цена. Клиент платит частями — каждая оплата сохраняется в
  истории, остаток долга = цена − сумма оплат (переплатить нельзя).
  С каждой оплаты:
    • fund1_rate% -> фонд 1 (по умолчанию 20%)
    • fund2_rate% -> фонд 2 (по умолчанию 5%)
    • остаток     -> деньги компании
  Ставки фондов фиксируются в платеже в момент поступления: смена настроек
  не переписывает историю.

  Рабочему: в проекте указано, сколько мы ему должны (worker_amount).
  Выплаты рабочему записываются вручную (WorkerPayout) и списываются из
  выбранной «корзины» (обычно деньги компании). Долг рабочему = должны − выплачено.
"""
import calendar
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


PERCENT_VALIDATORS = [MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))]


class GlobalSettings(models.Model):
    fund1_rate = models.DecimalField('Фонд 1 (%)', max_digits=5, decimal_places=2, default=Decimal('20.00'),
                                     validators=PERCENT_VALIDATORS)
    fund1_name = models.CharField('Название Фонд 1', max_length=50, default='Фонд 20%')

    fund2_rate = models.DecimalField('Фонд 2 (%)', max_digits=5, decimal_places=2, default=Decimal('5.00'),
                                     validators=PERCENT_VALIDATORS)
    fund2_name = models.CharField('Название Фонд 2', max_length=50, default='Фонд 5%')

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def money(value) -> Decimal:
    """Округление денежной величины до 2 знаков."""
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def add_months(d, months: int, day: int | None = None):
    """Прибавить к дате N календарных месяцев.

    `day` — «якорный» день месяца (например, день старта проекта): 31.01 → 28.02 → 31.03,
    без постепенного сползания на 28-е. Если день не существует в месяце — берётся последний.
    """
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return d.replace(year=year, month=month, day=min(day or d.day, last))


def is_month_end(d) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Суперадмин'
        WORKER = 'worker', 'Рабочий'

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.WORKER)
    full_name = models.CharField('ФИО', max_length=150, blank=True)
    phone = models.CharField('Телефон', max_length=30, blank=True)

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN

    def __str__(self):
        return self.full_name or self.username


class Bucket(models.TextChoices):
    FUND20 = 'fund20', 'Фонд 20%'
    FUND5 = 'fund5', 'Фонд 5%'
    COMPANY = 'company', 'Деньги компании'


class ProjectStatus(models.TextChoices):
    ACTIVE = 'active', 'В работе'
    DONE = 'done', 'Завершён'
    CANCELLED = 'cancelled', 'Отменён'


class Project(models.Model):
    name = models.CharField('Название проекта', max_length=200)
    worker = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='projects',
        limit_choices_to={'role': User.Role.WORKER}, verbose_name='Рабочий',
    )
    description = models.TextField('Описание', blank=True)

    # Клиент
    client_name = models.CharField('Клиент', max_length=200, blank=True)
    client_phone = models.CharField('Телефон клиента', max_length=30, blank=True)

    # Деньги
    price = models.DecimalField('Цена проекта', max_digits=14, decimal_places=2, default=Decimal('0'))
    worker_amount = models.DecimalField('Должны рабочему', max_digits=14, decimal_places=2, default=Decimal('0'))

    has_monthly = models.BooleanField('Ежемесячная оплата', default=False)
    monthly_amount = models.DecimalField('Оплата в месяц', max_digits=14, decimal_places=2, null=True, blank=True)
    monthly_next_due = models.DateField('Следующая ежемесячная оплата', null=True, blank=True)

    # Даты проекта
    start_date = models.DateField('Дата начала')
    deadline_date = models.DateField('Дедлайн (сдача)')
    beta_date = models.DateField('Показ бета-версии', null=True, blank=True)
    finished_date = models.DateField('Фактическая сдача рабочим', null=True, blank=True)

    status = models.CharField(max_length=10, choices=ProjectStatus.choices, default=ProjectStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def paid(self) -> Decimal:
        """Оплачено клиентом в счёт цены проекта (ежемесячные оплаты не входят)."""
        return sum((p.amount for p in self.payments.all() if p.kind != PaymentKind.MONTHLY), Decimal('0'))

    @property
    def debt(self) -> Decimal:
        return max(self.price - self.paid, Decimal('0'))

    @property
    def worker_paid(self) -> Decimal:
        return sum((p.amount for p in self.payouts.all()), Decimal('0'))

    @property
    def worker_debt(self) -> Decimal:
        return max(self.worker_amount - self.worker_paid, Decimal('0'))

    def deadline_status(self) -> dict:
        """Сравнение фактической сдачи (или сегодня) с дедлайном.

        Состояния: early (сдал раньше), ontime (в срок), late (позже),
        pending (ещё в работе, срок не вышел), overdue (просрочен, ещё не сдан).
        `days` — модуль разницы в днях.
        """
        today = timezone.localdate()
        dl = self.deadline_date
        if self.finished_date:
            diff = (dl - self.finished_date).days  # >0 сдал раньше срока
            state = 'early' if diff > 0 else ('ontime' if diff == 0 else 'late')
            return {'finished': True, 'state': state, 'days': abs(diff),
                    'finished_date': self.finished_date, 'deadline_date': dl}
        diff = (dl - today).days
        state = 'pending' if diff >= 0 else 'overdue'
        return {'finished': False, 'state': state, 'days': abs(diff), 'deadline_date': dl}

    def next_monthly_due(self):
        """Следующая дата ежемесячной оплаты после текущей (якорь — день старта проекта)."""
        base = self.monthly_next_due or self.start_date
        # если текущая дата «прижата» к концу короткого месяца — возвращаемся к дню старта
        day = max(base.day, self.start_date.day) if is_month_end(base) else base.day
        return add_months(base, 1, day=day)

    def save(self, *args, **kwargs):
        if self.has_monthly and self.monthly_next_due is None:
            self.monthly_next_due = self.start_date
        super().save(*args, **kwargs)


class PaymentKind(models.TextChoices):
    PAYMENT = 'payment', 'Оплата'
    MONTHLY = 'monthly', 'Ежемесячная оплата'
    # этапы из прежней схемы оплаты — только для истории старых платежей
    START = 'start', 'Старт'
    BETA = 'beta', 'Бета'
    FINAL = 'final', 'Сдача'


class Payment(models.Model):
    """Поступление денег от клиента с автоматическим распределением по фондам."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='payments')
    kind = models.CharField(max_length=10, choices=PaymentKind.choices, default=PaymentKind.PAYMENT)
    amount = models.DecimalField('Сумма', max_digits=14, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    note = models.CharField('Комментарий', max_length=255, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    # Ставки фондов на момент поступления (снимок настроек)
    fund1_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fund2_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Распределение (считается автоматически при создании / изменении суммы)
    fund20_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    fund5_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    company_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    @classmethod
    def from_db(cls, db, field_names, values):
        obj = super().from_db(db, field_names, values)
        obj._original = obj.amount
        return obj

    def distribute(self):
        """Рассчитать распределение суммы по фондам и компании."""
        if self.fund1_rate is None or self.fund2_rate is None:
            settings = GlobalSettings.load()
            self.fund1_rate = settings.fund1_rate
            self.fund2_rate = settings.fund2_rate

        amount = money(self.amount)
        self.fund20_amount = money(amount * (self.fund1_rate / Decimal('100')))
        self.fund5_amount = money(amount * (self.fund2_rate / Decimal('100')))
        self.company_amount = max(amount - self.fund20_amount - self.fund5_amount, Decimal('0.00'))

    def save(self, *args, **kwargs):
        # распределяем только новый платёж или при изменении суммы —
        # смена настроек фондов не переписывает историю
        if self._state.adding or getattr(self, '_original', None) != self.amount:
            self.distribute()
        super().save(*args, **kwargs)
        self._original = self.amount

    def __str__(self):
        return f'{self.get_kind_display()} — {self.amount} по «{self.project.name}»'


class WorkerPayout(models.Model):
    """Выплата рабочему по проекту (записывается вручную)."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='payouts')
    worker = models.ForeignKey(User, on_delete=models.PROTECT, related_name='payouts', verbose_name='Рабочий')
    amount = models.DecimalField('Сумма', max_digits=14, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    paid_from = models.CharField('Оплачено из', max_length=10, choices=Bucket.choices, default=Bucket.COMPANY)
    note = models.CharField('Комментарий', max_length=255, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f'{self.worker} — {self.amount} по «{self.project.name}»'


class ServerStatus(models.TextChoices):
    ACTIVE = 'active', 'Активен'
    EXPIRED = 'expired', 'Истёк'


class Server(models.Model):
    label = models.CharField('Название/назначение', max_length=200)
    login = models.CharField('Логин', max_length=200)
    password = models.CharField('Пароль', max_length=200)
    project = models.ForeignKey(
        Project, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='servers', verbose_name='Проект',
    )
    purchase_date = models.DateField('Дата покупки', default=timezone.localdate)
    days = models.PositiveIntegerField('Куплен на (дней)')
    expiry_date = models.DateField('Действует до')
    amount = models.DecimalField('Стоимость', max_digits=14, decimal_places=2, default=Decimal('0'))
    paid_from = models.CharField('Оплачено из', max_length=10, choices=Bucket.choices)
    status = models.CharField(max_length=10, choices=ServerStatus.choices, default=ServerStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['expiry_date']

    def save(self, *args, **kwargs):
        if not self.expiry_date and self.purchase_date and self.days:
            self.expiry_date = self.purchase_date + timedelta(days=self.days)
        super().save(*args, **kwargs)

    @property
    def days_left(self) -> int:
        return (self.expiry_date - timezone.localdate()).days

    def __str__(self):
        return self.label


class ServerRenewal(models.Model):
    """Продление сервера."""
    server = models.ForeignKey(Server, on_delete=models.CASCADE, related_name='renewals')
    date = models.DateField(default=timezone.localdate)
    days = models.PositiveIntegerField('Продлён на (дней)')
    new_expiry = models.DateField('Новая дата окончания')
    amount = models.DecimalField('Стоимость', max_digits=14, decimal_places=2, default=Decimal('0'))
    paid_from = models.CharField('Оплачено из', max_length=10, choices=Bucket.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']


class Notification(models.Model):
    class Kind(models.TextChoices):
        SERVER = 'server', 'Сервер'
        PROJECT = 'project', 'Проект'
        TASK = 'task', 'Задача'

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    dedup_key = models.CharField(max_length=200, unique=True)  # одно уведомление на веху
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


# --------------------------------------------------------------------------- #
#  Задачи (канбан-доска)
# --------------------------------------------------------------------------- #
class TaskStatus(models.TextChoices):
    TODO = 'todo', 'К выполнению'
    IN_PROGRESS = 'in_progress', 'В работе'
    REVIEW = 'review', 'На проверке'
    DONE = 'done', 'Готово'


class TaskPriority(models.TextChoices):
    LOW = 'low', 'Низкий'
    MEDIUM = 'medium', 'Средний'
    HIGH = 'high', 'Высокий'


class Task(models.Model):
    title = models.CharField('Задача', max_length=200)
    description = models.TextField('Описание', blank=True)
    assignee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tasks', verbose_name='Исполнитель')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_tasks', verbose_name='Автор')
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='tasks', verbose_name='Проект')
    status = models.CharField('Статус', max_length=12, choices=TaskStatus.choices, default=TaskStatus.TODO)
    priority = models.CharField('Приоритет', max_length=10, choices=TaskPriority.choices,
                                default=TaskPriority.MEDIUM)
    deadline = models.DateField('Дедлайн', null=True, blank=True)
    position = models.PositiveIntegerField(default=0)  # порядок внутри колонки
    completed_at = models.DateTimeField('Выполнена', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['position', '-created_at']
        indexes = [models.Index(fields=['assignee', 'status']), models.Index(fields=['completed_at'])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # время выполнения ставится при переходе в «Готово» и снимается при возврате
        if self.status == TaskStatus.DONE and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status != TaskStatus.DONE:
            self.completed_at = None
        super().save(*args, **kwargs)

    @property
    def completed_date(self):
        return timezone.localdate(self.completed_at) if self.completed_at else None

    def deadline_state(self) -> str | None:
        """on_time / late — для выполненных; overdue / today / soon / ok — для открытых."""
        if not self.deadline:
            return None
        if self.completed_at:
            return 'on_time' if self.completed_date <= self.deadline else 'late'
        left = (self.deadline - timezone.localdate()).days
        if left < 0:
            return 'overdue'
        if left == 0:
            return 'today'
        return 'soon' if left <= 2 else 'ok'


class SubTask(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='subtasks')
    title = models.CharField('Подзадача', max_length=200)
    is_done = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']

    def save(self, *args, **kwargs):
        if self.is_done and not self.done_at:
            self.done_at = timezone.now()
        elif not self.is_done:
            self.done_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
