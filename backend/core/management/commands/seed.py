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
            defaults=dict(role_admin=True, full_name='Супер Админ',
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
            username='aidos', defaults=dict(role_worker=True, full_name='Айдос Серіков'))
        if c1:
            w1.set_password('worker12345'); w1.save()
        w2, c2 = User.objects.get_or_create(
            username='dana', defaults=dict(role_worker=True, full_name='Дана Ахметова'))
        if c2:
            w2.set_password('worker12345'); w2.save()

        # тестировщики: любой из них проверяет любой проект
        for username, full_name in [('tester', 'Тимур Тестов'), ('tester2', 'Алия Проверкина')]:
            t, ct = User.objects.get_or_create(
                username=username, defaults=dict(role_tester=True, full_name=full_name))
            if ct:
                t.set_password('tester12345'); t.save()
                self.stdout.write(self.style.SUCCESS(f'Тестировщик: {username} / tester12345'))

        if Project.objects.exists():
            self.stdout.write('Демо-проекты уже созданы, пропускаю.')
            return

        # Создаём настройки по умолчанию
        GlobalSettings.load()

        # Проект 1: Этапы, есть старт, есть сервер
        p1 = Project.objects.create(
            name='Интернет-магазин «Sauda»', worker=w1,
            has_price=True, has_monthly=False, client_name='ТОО «Sauda»', client_phone='+7 701 111 22 33',
            price=Decimal('800000'), worker_amount=Decimal('140000'),
            start_date=today - timedelta(days=10),
            deadline_date=today + timedelta(days=20),
            beta_date=today + timedelta(days=10),
        )
        Payment.objects.create(project=p1, kind=PaymentKind.PAYMENT, amount=Decimal('100000'))
        Server.objects.create(
            project=p1, label='VPS для Sauda', login='root', password='S3rv3r!',
            purchase_date=today - timedelta(days=353), days=365,
            expiry_date=today + timedelta(days=6),  # уведомление «7 дней» рядом
            amount=Decimal('45000'), paid_from=Bucket.COMPANY,
        )

        # Проект 2: ежемесячная оплата
        p2 = Project.objects.create(
            name='CRM для клиники', worker=w2,
            has_price=False, has_monthly=True, client_phone='+7 702 333 44 55',
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
            has_price=True, has_monthly=True,
            price=Decimal('1000000'), worker_amount=Decimal('150000'),
            monthly_amount=Decimal('50000'),
            start_date=today - timedelta(days=5),
            deadline_date=today + timedelta(days=90),
            beta_date=today + timedelta(days=40),
        )
        p3.monthly_next_due = today + timedelta(days=25)
        p3.save()
        Payment.objects.create(project=p3, kind=PaymentKind.PAYMENT, amount=Decimal('200000'))

        self.stdout.write(self.style.SUCCESS('Демо-данные созданы.'))
