"""
Модели IT HubPro.

Финансовая логика (ключевое):
  У проекта одна цена (price). Клиент платит частями — каждая оплата сохраняется
  в истории, остаток долга = цена − сумма оплат (переплатить нельзя).
  С каждой оплаты:
    • фонд 1 и фонд 2 — процент от суммы (ставки проекта, а если не заданы —
      из общих настроек; по умолчанию 20% и 5%)
    • остаток -> деньги компании
  Ставки фиксируются в платеже в момент поступления: смена настроек не
  переписывает историю.

  Рабочему: в проекте указано, сколько мы ему должны (worker_amount).
  Выплаты рабочему записываются вручную (WorkerPayout) и списываются из
  выбранной «корзины» (обычно деньги компании). Долг рабочему = должны − выплачено.

Проверка (тестирование):
  Тестировщики к проектам не прикрепляются: любой тестировщик видит все проекты.
  Рабочий отправляет проект на проверку с комментарием, и первый тестировщик,
  который примет его или вернёт с замечаниями, решает судьбу проекта
  (он записывается в reviewer). Вся переписка хранится в ProjectComment.
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
        TESTER = 'tester', 'Тестировщик'

    # Роли совмещаются: один человек может быть и рабочим, и тестировщиком, и админом.
    role_admin = models.BooleanField('Админ', default=False)
    role_worker = models.BooleanField('Рабочий', default=False)
    role_tester = models.BooleanField('Тестировщик', default=False)
    full_name = models.CharField('ФИО', max_length=150, blank=True)
    phone = models.CharField('Телефон', max_length=30, blank=True)

    ROLE_FIELDS = {Role.ADMIN: 'role_admin', Role.WORKER: 'role_worker', Role.TESTER: 'role_tester'}

    @property
    def roles(self) -> list:
        """Роли пользователя в постоянном порядке: admin, worker, tester."""
        return [role for role, field in self.ROLE_FIELDS.items() if getattr(self, field)]

    def set_roles(self, roles):
        for role, field in self.ROLE_FIELDS.items():
            setattr(self, field, role in roles)

    @classmethod
    def with_role(cls, role):
        """Queryset пользователей с ролью: User.with_role('worker')."""
        return cls.objects.filter(**{cls.ROLE_FIELDS[role]: True})

    @property
    def is_admin(self) -> bool:
        return self.role_admin

    @property
    def is_worker(self) -> bool:
        return self.role_worker

    @property
    def is_tester(self) -> bool:
        return self.role_tester

    def __str__(self):
        return self.full_name or self.username


class Bucket(models.TextChoices):
    FUND20 = 'fund20', 'Фонд 20%'
    FUND5 = 'fund5', 'Фонд 5%'
    COMPANY = 'company', 'Деньги компании'


class Payer(models.TextChoices):
    """Кто платит за сервер: компания (из выбранного фонда) или клиент отдельно."""
    COMPANY = 'company', 'Компания'
    CLIENT = 'client', 'Клиент'


def term_end(start, months=None, days=None):
    """Конец срока: N календарных месяцев (6 мес, 1 год) или N дней от даты начала."""
    if months:
        return add_months(start, months)
    return start + timedelta(days=days or 0)


class ProjectStatus(models.TextChoices):
    ACTIVE = 'active', 'В работе'
    DONE = 'done', 'Завершён'
    CANCELLED = 'cancelled', 'Отменён'


class ReviewStatus(models.TextChoices):
    NONE = 'none', 'Не отправлен'
    REVIEW = 'review', 'На проверке'
    RETURNED = 'returned', 'Возврат'
    ACCEPTED = 'accepted', 'Принят'


class Project(models.Model):
    name = models.CharField('Название проекта', max_length=200)
    worker = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='projects',
        limit_choices_to={'role_worker': True}, verbose_name='Рабочий',
    )
    # кто последним принял или вернул проект (любой тестировщик или админ)
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_projects',
        verbose_name='Проверил',
    )
    review_status = models.CharField(
        'Проверка', max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.NONE)
    description = models.TextField('Описание', blank=True)

    # Клиент
    client_name = models.CharField('Клиент', max_length=150, blank=True)
    client_phone = models.CharField('Телефон клиента', max_length=30, blank=True)

    # Деньги: одна цена; клиент платит частями. 0 — цена ещё не указана
    price = models.DecimalField('Цена проекта', max_digits=14, decimal_places=2, default=Decimal('0'))
    worker_amount = models.DecimalField('Должны рабочему', max_digits=14, decimal_places=2, default=Decimal('0'))

    # Свои ставки фондов для проекта. Пусто — берутся из общих настроек.
    fund1_rate = models.DecimalField('Фонд 1 (%) для проекта', max_digits=5, decimal_places=2, null=True, blank=True)
    fund2_rate = models.DecimalField('Фонд 2 (%) для проекта', max_digits=5, decimal_places=2, null=True, blank=True)

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
    def total_price(self) -> Decimal:
        return self.price

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

    def fund_rates(self):
        """Ставки фондов проекта, а если не заданы — из общих настроек."""
        settings = GlobalSettings.load()
        return (self.fund1_rate if self.fund1_rate is not None else settings.fund1_rate,
                self.fund2_rate if self.fund2_rate is not None else settings.fund2_rate)

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


class ProjectComment(models.Model):
    """Запись в переписке по проекту: комментарий или шаг проверки."""
    class Kind(models.TextChoices):
        COMMENT = 'comment', 'Комментарий'
        SUBMIT = 'submit', 'Отправлено на проверку'
        ACCEPT = 'accept', 'Проект принят'
        RETURN = 'return', 'Возврат на доработку'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='project_comments')
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.COMMENT)
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class PaymentKind(models.TextChoices):
    PAYMENT = 'payment', 'Оплата'
    MONTHLY = 'monthly', 'Ежемесячная оплата'
    # старые этапы — остаются только в истории платежей
    START = 'start', 'Старт'
    BETA = 'beta', 'Бета'
    FINAL = 'final', 'Сдача'


# платежи «за проект» (не ежемесячные) — идут в счёт цены
PROJECT_KINDS = [PaymentKind.PAYMENT, PaymentKind.START, PaymentKind.BETA, PaymentKind.FINAL]


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
            self.fund1_rate, self.fund2_rate = self.project.fund_rates()

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
    months = models.PositiveIntegerField('Куплен на (месяцев)', null=True, blank=True)
    days = models.PositiveIntegerField('Куплен на (дней)')
    expiry_date = models.DateField('Действует до')
    amount = models.DecimalField('Стоимость', max_digits=14, decimal_places=2, default=Decimal('0'))
    paid_by = models.CharField('Кто платит', max_length=10, choices=Payer.choices, default=Payer.COMPANY)
    paid_from = models.CharField('Оплачено из', max_length=10, choices=Bucket.choices)
    status = models.CharField(max_length=10, choices=ServerStatus.choices, default=ServerStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['expiry_date']

    def save(self, *args, **kwargs):
        if self.months and self.purchase_date and not self.days:
            self.days = (term_end(self.purchase_date, months=self.months) - self.purchase_date).days
        if not self.expiry_date and self.purchase_date and self.days:
            self.expiry_date = term_end(self.purchase_date, self.months, self.days)
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
    months = models.PositiveIntegerField('Продлён на (месяцев)', null=True, blank=True)
    days = models.PositiveIntegerField('Продлён на (дней)')
    new_expiry = models.DateField('Новая дата окончания')
    amount = models.DecimalField('Стоимость', max_digits=14, decimal_places=2, default=Decimal('0'))
    paid_by = models.CharField('Кто платит', max_length=10, choices=Payer.choices, default=Payer.COMPANY)
    paid_from = models.CharField('Оплачено из', max_length=10, choices=Bucket.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']


class Notification(models.Model):
    class Kind(models.TextChoices):
        SERVER = 'server', 'Сервер'
        PROJECT = 'project', 'Проект'
        REVIEW = 'review', 'Проверка'
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


# --------------------------------------------------------------------------- #
#  Личный план на день / неделю
# --------------------------------------------------------------------------- #
class PlanPeriod(models.TextChoices):
    DAY = 'day', 'День'
    WEEK = 'week', 'Неделя'


def week_start(d):
    """Понедельник недели, в которую попадает дата."""
    return d - timedelta(days=d.weekday())


class PlanItem(models.Model):
    """Пункт личного плана. У каждого пользователя — свой список.

    date — день плана; для недельного плана — понедельник недели.
    carried — пункт не выполнили и перенесли в следующий период (там создана копия);
    в статистике своего периода он считается невыполненным.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='plan_items')
    period = models.CharField('Период', max_length=5, choices=PlanPeriod.choices, default=PlanPeriod.DAY)
    date = models.DateField('Дата')
    title = models.CharField('Что сделать', max_length=300)
    is_done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    carried = models.BooleanField('Перенесено', default=False)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']
        indexes = [models.Index(fields=['user', 'period', 'date'])]

    def save(self, *args, **kwargs):
        if self.period == PlanPeriod.WEEK and self.date:
            self.date = week_start(self.date)
        if self.is_done and not self.done_at:
            self.done_at = timezone.now()
        elif not self.is_done:
            self.done_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


# --------------------------------------------------------------------------- #
#  Расходы компании
# --------------------------------------------------------------------------- #
class ExpenseCategory(models.TextChoices):
    OFFICE = 'office', 'Аренда и офис'
    SALARY = 'salary', 'Зарплата и бонусы'
    MARKETING = 'marketing', 'Реклама и маркетинг'
    SERVICES = 'services', 'Сервисы и подписки'
    EQUIPMENT = 'equipment', 'Техника и оборудование'
    TAXES = 'taxes', 'Налоги и банк'
    OTHER = 'other', 'Прочее'


class Expense(models.Model):
    """Расход компании, записанный вручную: списывается из выбранного фонда."""
    date = models.DateField('Дата', default=timezone.localdate)
    amount = models.DecimalField('Сумма', max_digits=14, decimal_places=2)
    category = models.CharField('Категория', max_length=12, choices=ExpenseCategory.choices,
                                default=ExpenseCategory.OTHER)
    title = models.CharField('На что', max_length=200)
    note = models.CharField('Комментарий', max_length=255, blank=True)
    paid_from = models.CharField('Из какого фонда', max_length=10, choices=Bucket.choices, default=Bucket.COMPANY)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='expenses', verbose_name='Проект')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f'{self.title} — {self.amount}'
