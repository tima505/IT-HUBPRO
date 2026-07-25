from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    Bucket, GlobalSettings, Payment, PaymentKind, Project, Server, User,
)


class Command(BaseCommand):
    help = 'Создаёт суперадмина и демо-данные'

    def handle(self, *args, **options):
        today = timezone.localdate()

        admin, created = User.objects.get_or_create(
            username='admin',
            defaults=dict(role=User.Role.ADMIN, full_name='Супер Админ',
                          is_staff=True, is_superuser=True),
        )
        if created:
            admin.set_password('admin12345')
            admin.save()
            self.stdout.write(self.style.SUCCESS('Суперадмин: admin / admin12345'))
        else:
            self.stdout.write('Суперадмин уже существует (admin)')

        # рабочие
        w1, c1 = User.objects.get_or_create(
            username='aidos', defaults=dict(role=User.Role.WORKER, full_name='Айдос Серіков'))
        if c1:
            w1.set_password('worker12345'); w1.save()
        w2, c2 = User.objects.get_or_create(
            username='dana', defaults=dict(role=User.Role.WORKER, full_name='Дана Ахметова'))
        if c2:
            w2.set_password('worker12345'); w2.save()

        if Project.objects.exists():
            self.stdout.write('Демо-проекты уже созданы, пропускаю.')
            return

        # Создаём настройки по умолчанию
        GlobalSettings.load()

        # Проект 1: Этапы, есть старт, есть сервер
        p1 = Project.objects.create(
            name='Интернет-магазин «Sauda»', worker=w1,
            has_stages=True, has_monthly=False,
            worker_beta_amount=Decimal('80000'), worker_final_amount=Decimal('60000'),
            start_amount=Decimal('100000'), beta_amount=Decimal('400000'), final_amount=Decimal('300000'),
            start_date=today - timedelta(days=10),
            deadline_date=today + timedelta(days=20),
            beta_date=today + timedelta(days=10),
        )
        Payment.objects.create(project=p1, kind=PaymentKind.START, amount=Decimal('100000'))
        Server.objects.create(
            project=p1, label='VPS для Sauda', login='root', password='S3rv3r!',
            purchase_date=today - timedelta(days=353), days=365,
            expiry_date=today + timedelta(days=6),  # уведомление «7 дней» рядом
            amount=Decimal('45000'), paid_from=Bucket.COMPANY,
        )

        # Проект 2: ежемесячная оплата
        p2 = Project.objects.create(
            name='CRM для клиники', worker=w2,
            has_stages=False, has_monthly=True,
            worker_beta_amount=Decimal('0'), worker_final_amount=Decimal('0'),
            monthly_amount=Decimal('150000'),
            start_date=today - timedelta(days=2),
            deadline_date=today + timedelta(days=60),
            beta_date=today + timedelta(days=15),
        )
        p2.monthly_next_due = today + timedelta(days=3)  # уведомление «3 дня»
        p2.save()
        Payment.objects.create(project=p2, kind=PaymentKind.MONTHLY, amount=Decimal('150000'))

        # Проект 3: комбинированный (Этапы + Ежемесячно)
        p3 = Project.objects.create(
            name='ERP Система', worker=w1,
            has_stages=True, has_monthly=True,
            worker_beta_amount=Decimal('50000'), worker_final_amount=Decimal('100000'),
            start_amount=Decimal('200000'), beta_amount=Decimal('300000'), final_amount=Decimal('500000'),
            monthly_amount=Decimal('50000'),
            start_date=today - timedelta(days=5),
            deadline_date=today + timedelta(days=90),
            beta_date=today + timedelta(days=40),
        )
        p3.monthly_next_due = today + timedelta(days=25)
        p3.save()
        Payment.objects.create(project=p3, kind=PaymentKind.START, amount=Decimal('200000'))

        self.stdout.write(self.style.SUCCESS('Демо-данные созданы.'))
