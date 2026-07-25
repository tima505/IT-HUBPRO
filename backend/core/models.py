"""
Модели IT HubPro.

Финансовая логика (ключевое):
  С каждого платежа по проекту:
    • 20% суммы  -> фонд «20%»
    • 5%  суммы  -> фонд «5%»
    • доля рабочего = worker_percent% суммы  (только аванс и финальная оплата;
      для ежемесячной оплаты доля рабочего не выделяется — договариваются сами)
    • остаток -> деньги компании
  Итого: company = amount - fund20 - fund5 - worker_share
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
    worker_beta_amount = models.DecimalField('Оплата рабочему (Бета)', max_digits=14, decimal_places=2, default=Decimal('0'))
    worker_final_amount = models.DecimalField('Оплата рабочему (Сдача)', max_digits=14, decimal_places=2, default=Decimal('0'))
    # Настройки оплаты
    has_stages = models.BooleanField('Оплата по этапам', default=True)
    start_amount = models.DecimalField('Сумма (Старт)', max_digits=14, decimal_places=2, null=True, blank=True)
    beta_amount = models.DecimalField('Сумма (Бета)', max_digits=14, decimal_places=2, null=True, blank=True)
    final_amount = models.DecimalField('Сумма (Сдача)', max_digits=14, decimal_places=2, null=True, blank=True)

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
        if not self.has_stages:
            return Decimal('0.00')
        return (self.start_amount or Decimal('0')) + (self.beta_amount or Decimal('0')) + (self.final_amount or Decimal('0'))

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

    def save(self, *args, **kwargs):
        if self.has_monthly and self.monthly_next_due is None:
            self.monthly_next_due = self.start_date
        super().save(*args, **kwargs)


class PaymentKind(models.TextChoices):
    START = 'start', 'Старт'
    BETA = 'beta', 'Бета'
    FINAL = 'final', 'Сдача'
    MONTHLY = 'monthly', 'Ежемесячная оплата'


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
        fund20 = money(amount * (settings.fund1_rate / Decimal('100')))
        fund5 = money(amount * (settings.fund2_rate / Decimal('100')))
        remainder = amount - fund20 - fund5
        
        if self.kind == PaymentKind.BETA:
            worker = money(self.project.worker_beta_amount)
        elif self.kind == PaymentKind.FINAL:
            worker = money(self.project.worker_final_amount)
        else:
            worker = Decimal('0.00')
            
        company = remainder - worker
        self.fund20_amount = fund20
        self.fund5_amount = fund5
        self.worker_amount = worker
        self.company_amount = company

    def save(self, *args, **kwargs):
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

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    dedup_key = models.CharField(max_length=200, unique=True)  # одно уведомление на веху
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
