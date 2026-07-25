from datetime import date
from decimal import Decimal

from django.test import TestCase

from .models import Bucket, GlobalSettings, Payment, PaymentKind, Project, User
from .services import fund_balances


class FinanceLogicTests(TestCase):
    def setUp(self):
        self.worker = User.objects.create(username='w', role=User.Role.WORKER)
        # Убедимся что настройки по умолчанию (20% / 5%)
        GlobalSettings.load()

    def _project(self, has_stages=True, has_monthly=False, worker_beta=0, worker_final=0):
        return Project.objects.create(
            name='P', worker=self.worker, has_stages=has_stages, has_monthly=has_monthly,
            worker_beta_amount=Decimal(str(worker_beta)),
            worker_final_amount=Decimal(str(worker_final)),
            start_date=date(2026, 1, 1), deadline_date=date(2026, 2, 1),
        )

    def test_start_payment_no_worker(self):
        """Старт 100000: рабочий не получает ничего. 20000 / 5000 / 0 / 75000."""
        p = self._project(worker_beta=15000, worker_final=20000)
        pay = Payment.objects.create(project=p, kind=PaymentKind.START, amount=Decimal('100000'))
        self.assertEqual(pay.fund20_amount, Decimal('20000.00'))
        self.assertEqual(pay.fund5_amount, Decimal('5000.00'))
        self.assertEqual(pay.worker_amount, Decimal('0.00'))
        self.assertEqual(pay.company_amount, Decimal('75000.00'))
        total = pay.fund20_amount + pay.fund5_amount + pay.worker_amount + pay.company_amount
        self.assertEqual(total, Decimal('100000.00'))

    def test_beta_payment_worker_gets_fixed(self):
        """Бета 300000, рабочему 50000: 60000 / 15000 / 50000 / 175000."""
        p = self._project(worker_beta=50000, worker_final=30000)
        pay = Payment.objects.create(project=p, kind=PaymentKind.BETA, amount=Decimal('300000'))
        self.assertEqual(pay.fund20_amount, Decimal('60000.00'))
        self.assertEqual(pay.fund5_amount, Decimal('15000.00'))
        self.assertEqual(pay.worker_amount, Decimal('50000.00'))
        self.assertEqual(pay.company_amount, Decimal('175000.00'))

    def test_final_payment_worker_gets_fixed(self):
        """Финал 100000, рабочему 20000: 20000 / 5000 / 20000 / 55000."""
        p = self._project(worker_beta=50000, worker_final=20000)
        pay = Payment.objects.create(project=p, kind=PaymentKind.FINAL, amount=Decimal('100000'))
        self.assertEqual(pay.fund20_amount, Decimal('20000.00'))
        self.assertEqual(pay.fund5_amount, Decimal('5000.00'))
        self.assertEqual(pay.worker_amount, Decimal('20000.00'))
        self.assertEqual(pay.company_amount, Decimal('55000.00'))

    def test_monthly_no_worker(self):
        """Ежемесячная оплата: доли рабочего нет, только 20% / 5% / компания."""
        p = self._project(has_stages=False, has_monthly=True)
        pay = Payment.objects.create(project=p, kind=PaymentKind.MONTHLY, amount=Decimal('150000'))
        self.assertEqual(pay.fund20_amount, Decimal('30000.00'))
        self.assertEqual(pay.fund5_amount, Decimal('7500.00'))
        self.assertEqual(pay.worker_amount, Decimal('0.00'))
        self.assertEqual(pay.company_amount, Decimal('112500.00'))

    def test_custom_fund_rates(self):
        """Проверяем что из настроек берутся нестандартные ставки."""
        settings = GlobalSettings.load()
        settings.fund1_rate = Decimal('10.00')
        settings.fund2_rate = Decimal('10.00')
        settings.save()

        p = self._project(worker_beta=0, worker_final=0)
        pay = Payment.objects.create(project=p, kind=PaymentKind.START, amount=Decimal('100000'))
        self.assertEqual(pay.fund20_amount, Decimal('10000.00'))
        self.assertEqual(pay.fund5_amount, Decimal('10000.00'))
        self.assertEqual(pay.company_amount, Decimal('80000.00'))

    def test_fund_balances_aggregate(self):
        p = self._project(worker_beta=0, worker_final=0)
        Payment.objects.create(project=p, kind=PaymentKind.START, amount=Decimal('100000'))
        Payment.objects.create(project=p, kind=PaymentKind.FINAL, amount=Decimal('100000'))
        balances = fund_balances()
        self.assertEqual(balances[Bucket.FUND20]['balance'], Decimal('40000.00'))
        self.assertEqual(balances[Bucket.FUND5]['balance'], Decimal('10000.00'))
        self.assertEqual(balances[Bucket.COMPANY]['balance'], Decimal('150000.00'))
