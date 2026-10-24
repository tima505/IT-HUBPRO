"""
Модели IT HubPro.

Финансовая логика (ключевое):
  С каждого платежа по проекту:
    • фонд 1 и фонд 2 — процент от суммы (ставки проекта, а если не заданы —
      из общих настроек; по умолчанию 20% и 5%)
    • у проекта одна сумма (price) и одна сумма рабочему (worker_amount);
      клиент платит частями — с каждой оплаты рабочему идёт его доля
      пропорционально (оплатили 50% цены — рабочему 50% его суммы),
      последняя оплата закрывает остаток; с ежемесячных платежей — ничего;
      если сумму проекта или рабочему меняют позже, его доля с уже полученных
      оплат пересчитывается (фонды при этом не меняются)
    • остаток -> деньги компании
  Итого: company = amount - fund1 - fund2 - worker

Проверка (тестирование):
  Тестировщики к проектам не прикрепляются: любой тестировщик видит все проекты.
  Рабочий отправляет проект на проверку с комментарием, и первый тестировщик,
  который примет его или вернёт с замечаниями, решает судьбу проекта
  (он записывается в reviewer). Вся переписка хранится в ProjectComment.
"""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class GlobalSettings(models.Model):
    fund1_rate = models.DecimalField('Фонд 1 (%)', max_digits=5, decimal_places=2, default=Decimal('20.00'))
    fund1_name = models.CharField('Название Фонд 1', max_length=50, default='Фонд 20%')

    fund2_rate = models.DecimalField('Фонд 2 (%)', max_digits=5, decimal_places=2, default=Decimal('5.00'))
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


def add_months(d, months: int):
    """Прибавить к дате N календарных месяцев."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, 28)  # безопасный день, чтобы не выйти за границы месяца
    return d.replace(year=year, month=month, day=day)


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
    # Клиент
    client_name = models.CharField('Клиент', max_length=150, blank=True)
    client_phone = models.CharField('Телефон клиента', max_length=30, blank=True)

    # Оплата за проект: одна сумма; обе суммы можно указать позже или изменить
    has_price = models.BooleanField('Оплата за проект', default=True)
    price = models.DecimalField('Сумма проекта', max_digits=14, decimal_places=2, null=True, blank=True)
    worker_amount = models.DecimalField('Сумма рабочему', max_digits=14, decimal_places=2, null=True, blank=True)

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
        return (self.price or Decimal('0')) if self.has_price else Decimal('0')

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

    def recalc_worker_shares(self):
        """Пересчитать долю рабочего по уже полученным оплатам — после смены суммы проекта или рабочему.

        Фонды не трогаем: они зависят только от суммы оплаты. Меняется лишь то,
        как остаток делится между рабочим и компанией. Старые этапные платежи остаются как были.
        """
        done = list(self.payments.filter(kind__in=LEGACY_KINDS))
        for pay in self.payments.filter(kind=PaymentKind.PAYMENT).order_by('created_at', 'id'):
            pay.project = self  # считаем по только что сохранённым суммам
            remainder = pay.amount - pay.fund20_amount - pay.fund5_amount
            worker = pay.worker_share(pay.amount, remainder, earlier=done)
            if worker != pay.worker_amount:
                pay.worker_amount = worker
                pay.company_amount = remainder - worker
                pay.save(update_fields=['worker_amount', 'company_amount'])
            done.append(pay)

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


# платежи «за проект» (не ежемесячные): из них рабочий получает свою сумму
PROJECT_KINDS = [PaymentKind.PAYMENT, PaymentKind.START, PaymentKind.BETA, PaymentKind.FINAL]
# старые этапы: их доля рабочего была фиксированной и не пересчитывается
LEGACY_KINDS = [PaymentKind.START, PaymentKind.BETA, PaymentKind.FINAL]


class Payment(models.Model):
    """Поступление денег по проекту с автоматическим распределением."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='payments')
    kind = models.CharField(max_length=10, choices=PaymentKind.choices)
    amount = models.DecimalField('Сумма', max_digits=14, decimal_places=2)
    date = models.DateField(default=timezone.localdate)

    # Распределение (считается автоматически при сохранении)
    fund20_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    fund5_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    worker_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    company_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def distribute(self):
        """Рассчитать распределение суммы по фондам, рабочему и компании."""
        amount = money(self.amount)
        settings = GlobalSettings.load()
        # ставка проекта, если задана; иначе — из общих настроек
        rate1 = self.project.fund1_rate if self.project.fund1_rate is not None else settings.fund1_rate
        rate2 = self.project.fund2_rate if self.project.fund2_rate is not None else settings.fund2_rate
        fund20 = money(amount * (rate1 / Decimal('100')))
        fund5 = money(amount * (rate2 / Decimal('100')))
        remainder = amount - fund20 - fund5
        worker = self.worker_share(amount, remainder) if self.kind in PROJECT_KINDS else Decimal('0.00')
        company = remainder - worker
        self.fund20_amount = fund20
        self.fund5_amount = fund5
        self.worker_amount = worker
        self.company_amount = company

    def worker_share(self, amount, remainder, earlier=None) -> Decimal:
        """Доля рабочего с этой оплаты.

        Пропорционально: оплатили N% цены проекта — рабочему N% его суммы.
        Оплата, которая закрывает цену, отдаёт рабочему весь остаток.
        Цена не указана — рабочему идёт всё, что остаётся после фондов, пока не наберётся его сумма.
        earlier — оплаты, идущие раньше этой (по умолчанию все остальные оплаты за проект).
        """
        project = self.project
        total = money(project.worker_amount or 0)
        if total <= 0:
            return Decimal('0.00')
        if earlier is None:
            earlier = project.payments.filter(kind__in=PROJECT_KINDS).exclude(pk=self.pk)
        paid_to_worker = sum((p.worker_amount for p in earlier), Decimal('0'))
        left = total - paid_to_worker
        if left <= 0:
            return Decimal('0.00')
        price = project.price or Decimal('0')
        if price <= 0:
            return money(min(left, max(remainder, Decimal('0'))))
        paid_total = sum((p.amount for p in earlier), Decimal('0')) + amount
        if paid_total >= price:
            return money(left)
        return money(min(left, amount * total / price))

    def save(self, *args, **kwargs):
        # распределение считается один раз — при создании; история не пересчитывается
        if self._state.adding:
            self.distribute()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.get_kind_display()} — {self.amount} по «{self.project.name}»'


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
        REVIEW = 'review', 'Проверка'

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    dedup_key = models.CharField(max_length=200, unique=True)  # одно уведомление на веху
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
