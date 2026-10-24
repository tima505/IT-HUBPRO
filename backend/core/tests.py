from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (
    Bucket, GlobalSettings, Notification, Payment, PaymentKind, Project, Server, ServerRenewal,
    ServerStatus, User, WorkerPayout,
)
from .services import fund_balances, generate_notifications


class FinanceLogicTests(TestCase):
    def setUp(self):
        self.worker = User.objects.create(username='w', role_worker=True)
        GlobalSettings.load()
        self.p = Project.objects.create(name='P', worker=self.worker, price=Decimal('500000'),
                                        start_date=date(2026, 1, 1), deadline_date=date(2026, 2, 1))

    def test_payment_distribution(self):
        """Оплата 100 000: 20 000 / 5 000 / 75 000 компании."""
        pay = Payment.objects.create(project=self.p, amount=Decimal('100000'))
        self.assertEqual((pay.fund20_amount, pay.fund5_amount, pay.company_amount),
                         (Decimal('20000.00'), Decimal('5000.00'), Decimal('75000.00')))

    def test_custom_fund_rates(self):
        s = GlobalSettings.load()
        s.fund1_rate = Decimal('10.00')
        s.fund2_rate = Decimal('10.00')
        s.save()
        pay = Payment.objects.create(project=self.p, amount=Decimal('100000'))
        self.assertEqual((pay.fund20_amount, pay.fund5_amount, pay.company_amount),
                         (Decimal('10000.00'), Decimal('10000.00'), Decimal('80000.00')))

    def test_project_fund_rates_override_settings(self):
        """Ставки проекта важнее настроек: 30% / 10% со 100000 → 30000 / 10000 / 60000."""
        p = self.p
        p.fund1_rate = Decimal('30.00')
        p.fund2_rate = Decimal('10.00')
        p.save()
        pay = Payment.objects.create(project=p, amount=Decimal('100000'))
        self.assertEqual(pay.fund20_amount, Decimal('30000.00'))
        self.assertEqual(pay.fund5_amount, Decimal('10000.00'))
        self.assertEqual(pay.company_amount, Decimal('60000.00'))

    def test_fund_balances_include_payouts(self):
        Payment.objects.create(project=self.p, amount=Decimal('200000'))
        WorkerPayout.objects.create(project=self.p, worker=self.worker, amount=Decimal('30000'))
        b = fund_balances()
        self.assertEqual(b[Bucket.FUND20]['balance'], Decimal('40000.00'))
        self.assertEqual(b[Bucket.FUND5]['balance'], Decimal('10000.00'))
        self.assertEqual(b[Bucket.COMPANY]['balance'], Decimal('120000.00'))  # 150 000 − 30 000


# --------------------------------------------------------------------------- #
#  Регрессии: логические цепочки (деньги, даты, валидация API)
# --------------------------------------------------------------------------- #
class BaseAPITest(TestCase):
    def setUp(self):
        self.admin = User.objects.create(username='a', role_admin=True)
        self.worker = User.objects.create(username='w', role_worker=True)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.worker_api = APIClient()
        self.worker_api.force_authenticate(self.worker)
        self.p = Project.objects.create(
            name='P', worker=self.worker, price=Decimal('500000'), worker_amount=Decimal('100000'),
            client_name='Клиент', client_phone='+7 700 000 00 00',
            start_date=date(2026, 1, 31), deadline_date=date(2026, 3, 1))

    def post(self, url, data=None, client=None):
        return (client or self.api).post(url, data or {}, format='json')

    def pay(self, amount, **extra):
        return self.post(f'/api/projects/{self.p.id}/add_payment/', {'amount': amount, **extra})

    def pay_worker(self, amount, **extra):
        return self.post(f'/api/projects/{self.p.id}/pay_worker/', {'amount': amount, **extra})

    def income(self, amount):
        """Положить деньги в фонды/компанию через оплату клиента."""
        Payment.objects.create(project=self.p, amount=Decimal(amount))

    def server(self, **kw):
        defaults = dict(label='S', login='', password='', days=30, purchase_date=date(2026, 1, 1),
                        expiry_date=date(2026, 1, 31), amount=Decimal('0'), paid_from=Bucket.COMPANY)
        defaults.update(kw)
        return Server.objects.create(**defaults)


class PaymentChainTests(BaseAPITest):
    def test_partial_payments_reduce_debt_and_keep_history(self):
        """500 000: платят 100 + 200 + 100 + 100 тысяч → долг 0, история из 4 оплат."""
        expected_debts = ['400000.00', '200000.00', '100000.00', '0.00']
        for amount, debt in zip([100000, 200000, 100000, 100000], expected_debts):
            r = self.pay(amount)
            self.assertEqual(r.status_code, 201, r.json())
            self.assertEqual(r.json()['debt'], debt)
        data = r.json()
        self.assertEqual((data['paid'], data['paid_percent']), ('500000.00', 100))
        self.assertEqual([p['amount'] for p in data['payments']], ['100000.00'] * 2 + ['200000.00', '100000.00'])

    def test_cannot_overpay(self):
        self.pay(450000)
        r = self.pay(60000)
        self.assertEqual(r.status_code, 400)
        self.assertIn('50 000', r.json()['detail'])
        self.pay(50000)
        r = self.pay(1)
        self.assertIn('полностью оплачен', r.json()['detail'])

    def test_payment_date_and_note_saved(self):
        r = self.pay(1000, date='2026-02-10', note='Наличными')
        pay = r.json()['payments'][0]
        self.assertEqual((pay['date'], pay['note'], pay['kind']), ('2026-02-10', 'Наличными', 'payment'))
        future = (timezone.localdate() + timedelta(days=3)).isoformat()
        self.assertEqual(self.pay(1000, date=future).status_code, 400)

    def test_invalid_payments_rejected(self):
        for amount in (-5000, 0, 'abc'):
            r = self.pay(amount)
            self.assertEqual(r.status_code, 400, amount)
            self.assertIsInstance(r.json()['detail'], str)
        self.assertFalse(Payment.objects.exists())

    def test_settings_change_does_not_rewrite_history(self):
        pay = Payment.objects.create(project=self.p, amount=Decimal('100000'))
        s = GlobalSettings.load()
        s.fund1_rate = Decimal('50')
        s.save()
        pay.save()
        pay.refresh_from_db()
        self.assertEqual(pay.fund20_amount, Decimal('20000.00'))
        # изменение суммы пересчитывается по ставкам, действовавшим на момент платежа
        pay.amount = Decimal('200000')
        pay.save()
        self.assertEqual(pay.fund20_amount, Decimal('40000.00'))

    def test_delete_wrong_payment(self):
        pid = self.pay(100000).json()['payments'][0]['id']
        r = self.api.delete(f'/api/projects/{self.p.id}/payments/{pid}/')
        self.assertEqual((r.status_code, r.json()['debt']), (200, '500000.00'))

    def test_cannot_delete_spent_payment(self):
        pid = self.pay(100000).json()['payments'][0]['id']  # компании 75 000
        self.pay_worker(70000)
        r = self.api.delete(f'/api/projects/{self.p.id}/payments/{pid}/')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(Payment.objects.filter(pk=pid).exists())

    def test_price_cannot_drop_below_paid(self):
        self.pay(300000)
        r = self.api.patch(f'/api/projects/{self.p.id}/', {'price': 200000}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.patch(f'/api/projects/{self.p.id}/', {'price': 600000}, format='json')
        self.assertEqual(r.json()['debt'], '300000.00')

    def test_fund_rates_validated(self):
        r = self.api.put('/api/settings/', {'fund1_rate': 90, 'fund1_name': 'a',
                                            'fund2_rate': 90, 'fund2_name': 'b'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('100%', r.json()['detail'])
        r = self.api.put('/api/settings/', {'fund1_rate': -1, 'fund1_name': 'a',
                                            'fund2_rate': 5, 'fund2_name': 'b'}, format='json')
        self.assertEqual(r.status_code, 400)


class WorkerPayoutTests(BaseAPITest):
    def test_payouts_reduce_worker_debt(self):
        self.income(400000)  # компании 300 000
        self.assertEqual(self.pay_worker(40000, note='Аванс').json()['worker_debt'], '60000.00')
        data = self.pay_worker(60000).json()
        self.assertEqual((data['worker_paid'], data['worker_debt']), ('100000.00', '0.00'))
        self.assertEqual(len(data['payouts']), 2)
        self.assertEqual(fund_balances()[Bucket.COMPANY]['balance'], Decimal('200000.00'))

    def test_cannot_pay_worker_more_than_owed(self):
        self.income(400000)
        r = self.pay_worker(100001)
        self.assertEqual(r.status_code, 400)
        self.assertIn('100 000', r.json()['detail'])

    def test_cannot_pay_worker_without_money(self):
        r = self.pay_worker(50000)
        self.assertEqual(r.status_code, 400)
        self.assertIn('Недостаточно средств', r.json()['detail'])
        self.income(400000)  # фонд 5% = 20 000
        r = self.pay_worker(30000, paid_from='fund5')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.pay_worker(20000, paid_from='fund5').status_code, 201)

    def test_delete_payout_returns_debt(self):
        self.income(400000)
        oid = self.pay_worker(40000).json()['payouts'][0]['id']
        r = self.api.delete(f'/api/projects/{self.p.id}/payouts/{oid}/')
        self.assertEqual(r.json()['worker_debt'], '100000.00')

    def test_worker_amount_cannot_drop_below_paid(self):
        self.income(400000)
        self.pay_worker(80000)
        r = self.api.patch(f'/api/projects/{self.p.id}/', {'worker_amount': 50000}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_worker_sees_own_money_but_not_client_money(self):
        self.income(400000)
        self.pay_worker(30000)
        data = self.worker_api.get('/api/worker/dashboard/').json()
        self.assertEqual((data['total_earned'], data['total_owed']), (30000, 70000))
        project = data['projects'][0]
        self.assertEqual(project['worker_debt'], '70000.00')
        for hidden in ('price', 'debt', 'payments', 'totals'):
            self.assertNotIn(hidden, project)
        self.assertEqual(project['payouts'][0]['amount'], '30000.00')
        r = self.worker_api.get(f'/api/projects/{self.p.id}/').json()
        self.assertNotIn('price', r)

    def test_worker_cannot_record_payments(self):
        self.assertEqual(self.post(f'/api/projects/{self.p.id}/add_payment/', {'amount': 1}, self.worker_api).status_code, 403)
        self.assertEqual(self.post(f'/api/projects/{self.p.id}/pay_worker/', {'amount': 1}, self.worker_api).status_code, 403)


class ProjectCreateTests(BaseAPITest):
    def payload(self, **kw):
        data = {'name': 'Новый', 'worker': self.worker.id, 'price': 500000, 'worker_amount': 100000,
                'client_name': 'ИП Тест', 'client_phone': '+7 777', 'start_date': '2026-03-01',
                'deadline_date': '2026-04-01'}
        data.update(kw)
        return data

    def test_create_with_prepayment(self):
        r = self.api.post('/api/projects/', self.payload(prepayment=150000), format='json')
        self.assertEqual(r.status_code, 201, r.json())
        self.assertEqual((r.json()['paid'], r.json()['debt']), ('150000.00', '350000.00'))
        self.assertEqual(r.json()['payments'][0]['note'], 'Предоплата')

    def test_price_required_unless_monthly(self):
        self.assertEqual(self.api.post('/api/projects/', self.payload(price=0), format='json').status_code, 400)
        r = self.api.post('/api/projects/', self.payload(price=0, has_monthly=True, monthly_amount=50000), format='json')
        self.assertEqual(r.status_code, 201)

    def test_prepayment_not_above_price(self):
        r = self.api.post('/api/projects/', self.payload(prepayment=600000), format='json')
        self.assertEqual(r.status_code, 400)

    def test_server_can_be_paid_from_prepayment(self):
        """Предоплата 100 000 → компании 75 000 → сервер за 70 000 из денег компании можно купить."""
        r = self.api.post('/api/projects/', self.payload(
            prepayment=100000, has_server=True, server_days=30, server_amount=70000), format='json')
        self.assertEqual(r.status_code, 201, r.json())
        self.assertEqual(fund_balances()[Bucket.COMPANY]['balance'], Decimal('5000.00'))


class DebtsTests(BaseAPITest):
    def test_debts_grouped_by_client(self):
        other = Project.objects.create(name='P2', worker=self.worker, price=Decimal('200000'),
                                       client_name='клиент', client_phone='+7 700 000 00 00',
                                       start_date=date(2026, 1, 1), deadline_date=date(2026, 2, 1))
        Project.objects.create(name='Оплачен', worker=self.worker, price=Decimal('0'),
                               start_date=date(2026, 1, 1), deadline_date=date(2026, 2, 1))
        self.pay(100000)
        Payment.objects.create(project=other, amount=Decimal('50000'))
        data = self.api.get('/api/debts/').json()
        self.assertEqual(len(data['clients']), 1)  # «Клиент» и «клиент» с тем же телефоном — один
        client = data['clients'][0]
        self.assertEqual((client['debt'], len(client['projects'])), (550000, 2))
        self.assertEqual(data['clients_total'], 550000)
        self.assertEqual(data['workers_total'], 100000)
        self.assertEqual(self.worker_api.get('/api/debts/').status_code, 403)


class MonthlyTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.p.has_monthly = True
        self.p.save()  # monthly_next_due = 31.01

    def test_month_end_does_not_drift(self):
        for _ in range(3):
            self.post(f'/api/projects/{self.p.id}/pay_monthly/', {'amount': 1000})
        self.p.refresh_from_db()
        self.assertEqual(self.p.monthly_next_due, date(2026, 4, 30))
        self.post(f'/api/projects/{self.p.id}/pay_monthly/', {'amount': 1000})
        self.p.refresh_from_db()
        self.assertEqual(self.p.monthly_next_due, date(2026, 5, 31))

    def test_pay_monthly_without_amount(self):
        r = self.post(f'/api/projects/{self.p.id}/pay_monthly/')
        self.assertEqual(r.status_code, 400)
        self.p.refresh_from_db()
        self.assertEqual(self.p.monthly_next_due, date(2026, 1, 31))  # срок не сдвинулся

    def test_pay_monthly_uses_project_amount(self):
        self.p.monthly_amount = Decimal('150000')
        self.p.save()
        self.assertEqual(self.post(f'/api/projects/{self.p.id}/pay_monthly/').status_code, 200)
        self.assertEqual(self.p.payments.get().amount, Decimal('150000.00'))


class ServerTests(BaseAPITest):
    def test_cannot_overspend_fund(self):
        r = self.api.post('/api/servers/', {'label': 'S', 'days': 30, 'purchase_date': '2026-01-01',
                                            'amount': 99999, 'paid_from': 'fund5'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('доступно 0 ₸, нужно 99 999 ₸', r.json()['detail'])

    def test_can_spend_available_balance(self):
        self.income(100000)  # фонд 5% = 5 000
        r = self.api.post('/api/servers/', {'label': 'S', 'days': 30, 'purchase_date': '2026-01-01',
                                            'amount': 5000, 'paid_from': 'fund5'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(fund_balances()[Bucket.FUND5]['balance'], Decimal('0'))

    def test_edit_server_amount_counts_own_previous_expense(self):
        self.income(100000)
        s = self.server(amount=Decimal('5000'), paid_from=Bucket.FUND5)  # фонд 5% теперь 0
        r = self.api.patch(f'/api/servers/{s.id}/', {'amount': 4000}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_project_with_server_checks_balance(self):
        r = self.api.post('/api/projects/', {
            'name': 'X', 'worker': self.worker.id, 'start_date': '2026-01-01', 'deadline_date': '2026-02-01',
            'has_server': True, 'server_days': 30, 'server_amount': 1000, 'server_paid_from': 'fund20',
        }, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Project.objects.count(), 1)

    def test_renew_validation(self):
        s = self.server()
        for data in ({'days': 'abc'}, {'days': 0}, {'days': 30, 'paid_from': 'abc'},
                     {'days': 30, 'amount': -1}, {'days': 30, 'amount': 5000}):
            r = self.post(f'/api/servers/{s.id}/renew/', data)
            self.assertEqual(r.status_code, 400, data)
        self.assertFalse(ServerRenewal.objects.exists())

    def test_update_days_shifts_expiry_keeping_renewals(self):
        s = self.server(expiry_date=date(2026, 3, 2))  # 31.01 + продление 30 дней
        self.api.patch(f'/api/servers/{s.id}/', {'days': 60}, format='json')
        s.refresh_from_db()
        self.assertEqual(s.expiry_date, date(2026, 4, 1))

    def test_expired_status(self):
        s = self.server(expiry_date=date(2020, 1, 1))
        self.assertEqual(self.api.get(f'/api/servers/{s.id}/').json()['status'], ServerStatus.EXPIRED)
        self.income(100000)
        self.post(f'/api/servers/{s.id}/renew/', {'days': 30})
        self.assertEqual(self.api.get(f'/api/servers/{s.id}/').json()['status'], ServerStatus.ACTIVE)


class NotificationTests(BaseAPITest):
    def test_missed_milestone_still_notifies_once(self):
        today = timezone.localdate()
        self.server(expiry_date=today + timedelta(days=5))  # день «7» никто не открывал
        generate_notifications()
        generate_notifications()
        n = Notification.objects.get()
        self.assertIn('5 дней', n.message)

    def test_overdue_server_and_project(self):
        today = timezone.localdate()
        self.server(expiry_date=today - timedelta(days=2))
        self.p.has_monthly = True
        self.p.monthly_next_due = today - timedelta(days=1)
        self.p.save()
        generate_notifications()
        titles = set(Notification.objects.values_list('title', flat=True))
        self.assertEqual(titles, {'Сервер истёк', 'Просрочена оплата проекта'})

    def test_no_notification_before_first_milestone(self):
        self.server(expiry_date=timezone.localdate() + timedelta(days=30))
        generate_notifications()
        self.assertFalse(Notification.objects.exists())


class ProjectFlowTests(BaseAPITest):
    def project_payload(self, **kw):
        data = {'name': 'X', 'worker': self.worker.id, 'start_date': '2026-03-01', 'deadline_date': '2026-04-01'}
        data.update(kw)
        return data

    def test_dates_validated(self):
        for kw in ({'deadline_date': '2026-01-01'}, {'beta_date': '2026-02-01'}, {'beta_date': '2026-05-01'}):
            r = self.api.post('/api/projects/', self.project_payload(**kw), format='json')
            self.assertEqual(r.status_code, 400, kw)
        r = self.api.patch(f'/api/projects/{self.p.id}/', {'deadline_date': '2026-01-01'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_finish_with_date(self):
        r = self.post(f'/api/projects/{self.p.id}/finish/', {'date': '2026-02-20'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['deadline_status']['state'], 'early')

    def test_finish_bad_dates(self):
        future = (timezone.localdate() + timedelta(days=5)).isoformat()
        for d in ('abc', '2026-01-01', future):
            r = self.post(f'/api/projects/{self.p.id}/finish/', {'date': d})
            self.assertEqual(r.status_code, 400, d)

    def test_worker_finishes_only_through_review(self):
        r = self.post(f'/api/projects/{self.p.id}/finish/', {}, client=self.worker_api)
        self.assertEqual(r.status_code, 400)
        self.assertIn('проверку', r.json()['detail'])
        self.assertEqual(self.post(f'/api/projects/{self.p.id}/finish/', {'clear': True}).status_code, 200)

    def test_complete_sets_finished_date(self):
        self.post(f'/api/projects/{self.p.id}/complete/')
        self.p.refresh_from_db()
        self.assertEqual(self.p.finished_date, timezone.localdate())

    def test_delete_worker_with_projects(self):
        r = self.api.delete(f'/api/users/{self.worker.id}/')
        self.assertEqual(r.status_code, 400)
        self.assertIn('проекты', r.json()['detail'])


# --------------------------------------------------------------------------- #
#  Задачи
# --------------------------------------------------------------------------- #
from datetime import datetime

from .models import SubTask, Task, TaskStatus


class TaskTests(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.other = User.objects.create(username='o', role_worker=True)
        self.other_api = APIClient()
        self.other_api.force_authenticate(self.other)

    def create(self, client=None, **data):
        return (client or self.api).post('/api/tasks/', data, format='json')

    def test_admin_assigns_task_and_worker_notified(self):
        r = self.create(title='Сверстать лендинг', assignee=self.worker.id, deadline='2026-11-10')
        self.assertEqual(r.status_code, 201, r.json())
        n = Notification.objects.get(recipient=self.worker)
        self.assertEqual(n.title, 'Новая задача')

    def test_admin_must_choose_assignee(self):
        r = self.create(title='X')
        self.assertEqual(r.status_code, 400)

    def test_worker_sees_only_own_tasks(self):
        self.create(title='Моя', assignee=self.worker.id)
        self.create(title='Чужая', assignee=self.other.id)
        titles = [t['title'] for t in self.worker_api.get('/api/tasks/').json()]
        self.assertEqual(titles, ['Моя'])
        self.assertEqual(len(self.api.get('/api/tasks/').json()), 2)

    def test_worker_creates_only_for_self(self):
        r = self.create(self.worker_api, title='Себе')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['assignee'], self.worker.id)
        self.assertFalse(Notification.objects.exists())  # сам себе — без уведомления
        r = self.create(self.worker_api, title='Другому', assignee=self.other.id)
        self.assertEqual(r.status_code, 400)

    def test_worker_cannot_link_foreign_project(self):
        foreign = Project.objects.create(name='F', worker=self.other, start_date=date(2026, 1, 1),
                                         deadline_date=date(2026, 2, 1))
        r = self.create(self.worker_api, title='X', project=foreign.id)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.create(self.worker_api, title='X', project=self.p.id).status_code, 201)

    def test_worker_cannot_touch_foreign_task(self):
        tid = self.create(title='Чужая', assignee=self.other.id).json()['id']
        self.assertEqual(self.worker_api.patch(f'/api/tasks/{tid}/', {'status': 'done'}, format='json').status_code, 404)
        r = self.worker_api.post('/api/subtasks/', {'task': tid, 'title': 'x'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_worker_cannot_delete_admin_task(self):
        tid = self.create(title='От админа', assignee=self.worker.id).json()['id']
        self.assertEqual(self.worker_api.delete(f'/api/tasks/{tid}/').status_code, 403)
        own = self.create(self.worker_api, title='Своя').json()['id']
        self.assertEqual(self.worker_api.delete(f'/api/tasks/{own}/').status_code, 204)

    def test_done_sets_and_clears_completed_at(self):
        tid = self.create(title='X', assignee=self.worker.id).json()['id']
        r = self.worker_api.patch(f'/api/tasks/{tid}/', {'status': 'done'}, format='json')
        self.assertIsNotNone(r.json()['completed_at'])
        r = self.worker_api.patch(f'/api/tasks/{tid}/', {'status': 'in_progress'}, format='json')
        self.assertIsNone(r.json()['completed_at'])

    def test_reorder_moves_between_columns(self):
        a = self.create(title='A', assignee=self.worker.id).json()['id']
        b = self.create(title='B', assignee=self.worker.id).json()['id']
        r = self.post('/api/tasks/reorder/', {'status': 'in_progress', 'ids': [b, a]}, client=self.worker_api)
        self.assertEqual(r.status_code, 200)
        moved = {t.id: (t.status, t.position) for t in Task.objects.all()}
        self.assertEqual(moved, {b: ('in_progress', 0), a: ('in_progress', 1)})

    def test_reorder_rejects_foreign_and_bad_status(self):
        foreign = self.create(title='F', assignee=self.other.id).json()['id']
        r = self.post('/api/tasks/reorder/', {'status': 'done', 'ids': [foreign]}, client=self.worker_api)
        self.assertEqual(r.status_code, 400)
        r = self.post('/api/tasks/reorder/', {'status': 'xxx', 'ids': []}, client=self.worker_api)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Task.objects.get().status, 'todo')

    def test_subtasks_progress(self):
        tid = self.create(self.worker_api, title='X').json()['id']
        s1 = self.worker_api.post('/api/subtasks/', {'task': tid, 'title': 'Шаг 1'}, format='json').json()
        self.worker_api.post('/api/subtasks/', {'task': tid, 'title': 'Шаг 2'}, format='json')
        self.worker_api.patch(f'/api/subtasks/{s1["id"]}/', {'is_done': True}, format='json')
        t = self.worker_api.get(f'/api/tasks/{tid}/').json()
        self.assertEqual((t['subtasks_done'], t['subtasks_total']), (1, 2))
        self.assertEqual([st['title'] for st in t['subtasks']], ['Шаг 1', 'Шаг 2'])
        self.assertIsNotNone(SubTask.objects.get(pk=s1['id']).done_at)

    def test_deadline_notifications(self):
        today = timezone.localdate()
        Task.objects.create(title='Завтра', assignee=self.worker, deadline=today + timedelta(days=1))
        Task.objects.create(title='Горит', assignee=self.worker, deadline=today - timedelta(days=2))
        Task.objects.create(title='Готово', assignee=self.worker, deadline=today, status=TaskStatus.DONE)
        r = self.worker_api.get('/api/notifications/unread_count/')
        self.assertEqual(r.json()['count'], 2)
        titles = set(Notification.objects.filter(recipient=self.worker).values_list('title', flat=True))
        self.assertEqual(titles, {'Дедлайн завтра', 'Задача просрочена'})


class TaskReportTests(BaseAPITest):
    def done_task(self, user, completed, deadline=None, created=None):
        t = Task.objects.create(title='T', assignee=user, deadline=deadline, status=TaskStatus.DONE)
        tz = timezone.get_current_timezone()
        Task.objects.filter(pk=t.pk).update(
            completed_at=datetime(*completed, 12, tzinfo=tz),
            created_at=datetime(*(created or completed), 12, tzinfo=tz))
        return t

    def test_monthly_report(self):
        other = User.objects.create(username='o', full_name='Олжас', role_worker=True)
        self.done_task(self.worker, (2026, 9, 3), deadline=date(2026, 9, 5), created=(2026, 9, 1))  # в срок, 2 дня
        self.done_task(self.worker, (2026, 9, 10), deadline=date(2026, 9, 8), created=(2026, 9, 6))  # поздно, 4 дня
        self.done_task(self.worker, (2026, 9, 10))                                     # без дедлайна
        self.done_task(other, (2026, 9, 20))
        self.done_task(self.worker, (2026, 8, 31))                                     # другой месяц
        Task.objects.create(title='Просрочено', assignee=other, deadline=date(2026, 9, 25))

        data = self.api.get('/api/tasks/report/?month=2026-09').json()
        self.assertEqual(data['totals']['done'], 4)
        self.assertEqual(data['totals']['late'], 1)
        self.assertEqual(data['totals']['overdue'], 1)
        self.assertEqual(data['totals']['on_time_rate'], 75)
        w = next(p for p in data['people'] if p['id'] == self.worker.id)
        self.assertEqual((w['done'], w['on_time'], w['late'], w['on_time_rate']), (3, 2, 1, 67))
        self.assertEqual(data['people'][0]['id'], self.worker.id)  # лидер — больше всех сделал
        by_day = {d['date']: d['done'] for d in data['by_day']}
        self.assertEqual(len(by_day), 30)
        self.assertEqual(by_day['2026-09-10'], 2)

    def test_worker_report_only_self(self):
        User.objects.create(username='o', role_worker=True)
        data = self.worker_api.get('/api/tasks/report/').json()
        self.assertEqual([p['id'] for p in data['people']], [self.worker.id])

    def test_bad_month(self):
        self.assertEqual(self.api.get('/api/tasks/report/?month=2026-13').status_code, 400)
        self.assertEqual(self.api.get('/api/tasks/report/?month=abc').status_code, 400)


# --------------------------------------------------------------------------- #
#  Проверка тестировщиком, совмещённые роли, пользователи
# --------------------------------------------------------------------------- #
def client_for(user):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user)
    return client


class ReviewFlowTests(TestCase):
    """Проверка: любой тестировщик видит и проверяет любой проект, решает первый."""

    def setUp(self):
        self.admin = User.objects.create(username='adm', role_admin=True)
        self.tester = User.objects.create(username='t', role_tester=True)
        self.tester2 = User.objects.create(username='t2', role_tester=True)
        self.worker = User.objects.create(username='wk', role_worker=True)
        self.other_worker = User.objects.create(username='wk2', role_worker=True)
        self.project = Project.objects.create(
            name='R', worker=self.worker, client_phone='+7 777 000 00 00',
            price=Decimal('100000'), worker_amount=Decimal('5000'),
            start_date=date(2026, 1, 1), deadline_date=date(2026, 2, 1),
        )
        self.url = f'/api/projects/{self.project.id}/'
        self.as_admin, self.as_worker = client_for(self.admin), client_for(self.worker)
        self.as_tester, self.as_tester2 = client_for(self.tester), client_for(self.tester2)

    def submit(self, text='Готово'):
        return self.as_worker.post(self.url + 'submit/', {'text': text}, format='json')

    def test_full_cycle(self):
        # без комментария отправить нельзя
        self.assertEqual(self.as_worker.post(self.url + 'submit/', {}, format='json').status_code, 400)
        r = self.submit('Сделал корзину')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['review_status'], 'review')
        self.assertIsNotNone(r.data['finished_date'])
        # уведомление получили ВСЕ тестировщики
        self.assertEqual(Notification.objects.filter(recipient=self.tester).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.tester2).count(), 1)

        # возврат без замечаний запрещён
        r = self.as_tester.post(self.url + 'review/', {'decision': 'return'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.as_tester.post(self.url + 'review/', {'decision': 'return', 'text': 'Не работает оплата'}, format='json')
        self.assertEqual(r.data['review_status'], 'returned')
        self.assertEqual(r.data['reviewer'], self.tester.id)
        self.assertIsNone(r.data['finished_date'])
        self.assertTrue(Notification.objects.filter(recipient=self.worker, title='Проект возвращён').exists())

        # повторная отправка — принимает уже другой тестировщик
        self.submit('Исправил оплату')
        r = self.as_tester2.post(self.url + 'review/', {'decision': 'accept'}, format='json')
        self.assertEqual(r.data['review_status'], 'accepted')
        self.assertEqual(r.data['reviewer'], self.tester2.id)
        self.assertIsNotNone(r.data['finished_date'])
        self.assertEqual([c['kind'] for c in r.data['comments']], ['submit', 'return', 'submit', 'accept'])
        # принятый проект повторно не отправляется
        self.assertEqual(self.submit('x').status_code, 400)

    def test_first_tester_decides(self):
        self.submit()
        self.assertEqual(self.as_tester.post(self.url + 'review/', {'decision': 'accept'}, format='json').status_code, 200)
        # второй тестировщик опоздал: проект уже принят
        r = self.as_tester2.post(self.url + 'review/', {'decision': 'return', 'text': 'нашёл баг'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('уже принят', r.data['detail'])
        self.project.refresh_from_db()
        self.assertEqual(self.project.review_status, 'accepted')
        self.assertEqual(self.project.reviewer, self.tester)

    def test_access(self):
        # любой тестировщик видит проект; чужой рабочий — нет
        self.assertEqual(self.as_tester2.get(self.url).status_code, 200)
        self.assertEqual(client_for(self.other_worker).get(self.url).status_code, 404)
        self.submit()
        # рабочий не проверяет сам себя, тестировщик не отправляет за рабочего
        self.assertEqual(self.as_worker.post(self.url + 'review/', {'decision': 'accept'}, format='json').status_code, 403)
        self.assertEqual(self.as_tester.post(self.url + 'submit/', {'text': 'x'}, format='json').status_code, 403)
        # рабочий не отмечает сдачу в обход проверки
        self.assertEqual(self.as_worker.post(self.url + 'finish/', {}, format='json').status_code, 400)
        # менять проект рабочий и тестировщик не могут
        self.assertEqual(self.as_tester.patch(self.url, {'name': 'x'}, format='json').status_code, 403)
        # отменённые проекты тестировщикам не показываются
        Project.objects.filter(pk=self.project.pk).update(status='cancelled')
        self.assertEqual(self.as_tester.get(self.url).status_code, 404)

    def test_money_is_hidden(self):
        Payment.objects.create(project=self.project, kind=PaymentKind.PAYMENT, amount=Decimal('100000'))
        t = self.as_tester.get(self.url).data
        for field in ('totals', 'payments', 'payouts', 'servers', 'price', 'worker_amount', 'client_phone'):
            self.assertNotIn(field, t)
        w = self.as_worker.get(self.url).data
        for field in ('payments', 'price', 'debt', 'totals'):
            self.assertNotIn(field, w)
        self.assertEqual(w['client_phone'], '+7 777 000 00 00')
        self.assertEqual((w['worker_amount'], w['worker_paid'], w['worker_debt']),
                         ('5000.00', '0.00', '5000.00'))

    def test_comments(self):
        # пишет тестировщик — узнаёт рабочий
        r = self.as_tester.post(self.url + 'comment/', {'text': 'Когда ждать?'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['comments'][0]['kind'], 'comment')
        self.assertEqual(Notification.objects.filter(recipient=self.worker).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.tester2).count(), 0)
        # пишет рабочий — пока никто не проверял, узнают все тестировщики
        self.as_worker.post(self.url + 'comment/', {'text': 'Завтра'}, format='json')
        self.assertEqual(Notification.objects.filter(recipient=self.tester).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.tester2).count(), 1)
        self.assertEqual(client_for(self.other_worker).post(self.url + 'comment/', {'text': 'x'}, format='json').status_code, 404)

    def test_history(self):
        Payment.objects.create(project=self.project, kind=PaymentKind.PAYMENT, amount=Decimal('100000'))
        self.submit()
        r = self.as_admin.get('/api/history/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual({e['type'] for e in r.data}, {'project', 'payment', 'review'})
        self.assertEqual(self.as_worker.get('/api/history/').status_code, 403)
        self.assertEqual(self.as_tester.get('/api/history/').status_code, 403)


class MultiRoleTests(TestCase):
    def setUp(self):
        self.both = User.objects.create(username='both', role_worker=True, role_tester=True)
        self.other = User.objects.create(username='other', role_worker=True)
        self.tester = User.objects.create(username='t', role_tester=True)
        dates = dict(start_date=date(2026, 1, 1), deadline_date=date(2026, 2, 1))
        self.mine = Project.objects.create(name='Мой', worker=self.both, worker_amount=Decimal('7'), **dates)
        self.theirs = Project.objects.create(name='Чужой', worker=self.other, **dates)
        self.cancelled = Project.objects.create(name='Отменён', worker=self.other, status='cancelled', **dates)
        self.as_both = client_for(self.both)

    def test_sees_own_and_others(self):
        data = {p['name']: p for p in self.as_both.get('/api/projects/').data}
        self.assertEqual(set(data), {'Мой', 'Чужой'})
        self.assertIn('worker_debt', data['Мой'])       # свой — как рабочему, со своей суммой
        self.assertNotIn('worker_debt', data['Чужой'])  # чужой — как тестировщику, без денег
        self.assertEqual(len(self.as_both.get('/api/worker/dashboard/').data['projects']), 1)

    def test_cannot_review_own_project(self):
        mine = f'/api/projects/{self.mine.id}/'
        self.as_both.post(mine + 'submit/', {'text': 'готово'}, format='json')
        self.assertEqual(self.as_both.post(mine + 'review/', {'decision': 'accept'}, format='json').status_code, 403)
        # уведомление о своей отправке себе не приходит, другому тестировщику — приходит
        self.assertFalse(Notification.objects.filter(recipient=self.both).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.tester).exists())
        # а чужой проект проверить может
        theirs = f'/api/projects/{self.theirs.id}/'
        client_for(self.other).post(theirs + 'submit/', {'text': 'готово'}, format='json')
        self.assertEqual(self.as_both.post(theirs + 'review/', {'decision': 'accept'}, format='json').status_code, 200)

    def test_tester_only_has_no_admin_access(self):
        self.assertEqual(client_for(self.tester).get('/api/users/').status_code, 403)
        self.assertEqual(client_for(self.tester).get('/api/finance/').status_code, 403)


class UserManageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create(username='adm', role_admin=True)
        self.admin.set_password('oldpass1')
        self.admin.save()
        self.client = client_for(self.admin)

    def _create(self, **data):
        return self.client.post('/api/users/', {'password': 'secret1', **data}, format='json')

    def test_create_roles(self):
        r = self._create(username='boss', full_name='Босс', roles=['admin'])
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(User.objects.get(username='boss').check_password('secret1'))
        # без пароля, с коротким паролем или без ролей — нельзя
        self.assertEqual(self._create(username='x', roles=['worker'], password='').status_code, 400)
        self.assertEqual(self._create(username='x', roles=['worker'], password='123').status_code, 400)
        self.assertEqual(self._create(username='x', roles=[]).status_code, 400)
        self.assertEqual(self._create(username='x').status_code, 400)

        # роли совмещаются в любом сочетании
        r = self._create(username='all', roles=['tester', 'worker', 'admin'])
        self.assertEqual(r.data['roles'], ['admin', 'worker', 'tester'])
        self.assertEqual(r.data['roles_display'], 'Суперадмин, Рабочий, Тестировщик')
        w = self._create(username='dev', roles=['worker']).data
        self._create(username='qa', roles=['tester'])
        self.assertEqual(len(self.client.get('/api/users/?role=worker').data), 2)
        self.assertEqual(len(self.client.get('/api/users/?role=tester').data), 2)

        # роли можно менять после создания
        r = self.client.patch(f"/api/users/{w['id']}/", {'roles': ['worker', 'tester']}, format='json')
        self.assertEqual(r.data['roles'], ['worker', 'tester'])
        self.assertEqual(self.client.patch(f"/api/users/{w['id']}/", {'roles': []}, format='json').status_code, 400)

    def test_role_guards(self):
        # снять «Рабочего» у того, за кем есть проекты, нельзя
        w = User.objects.create(username='w', role_worker=True)
        Project.objects.create(name='P', worker=w, start_date=date(2026, 1, 1), deadline_date=date(2026, 2, 1))
        r = self.client.patch(f'/api/users/{w.id}/', {'roles': ['tester']}, format='json')
        self.assertEqual(r.status_code, 400)
        # добавить роль можно
        r = self.client.patch(f'/api/users/{w.id}/', {'roles': ['worker', 'tester']}, format='json')
        self.assertEqual(r.status_code, 200)
        # с себя роль админа не снять
        r = self.client.patch(f'/api/users/{self.admin.id}/', {'roles': ['worker']}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertTrue(User.objects.get(id=self.admin.id).is_admin)

    def test_delete_guards(self):
        self.assertEqual(self.client.delete(f'/api/users/{self.admin.id}/').status_code, 400)
        w = User.objects.create(username='w', role_worker=True)
        Project.objects.create(name='P', worker=w, start_date=date(2026, 1, 1), deadline_date=date(2026, 2, 1))
        self.assertEqual(self.client.delete(f'/api/users/{w.id}/').status_code, 400)
        t = User.objects.create(username='t', role_tester=True)
        self.assertEqual(self.client.delete(f'/api/users/{t.id}/').status_code, 204)

    def test_profile(self):
        r = self.client.patch('/api/auth/me/', {'full_name': 'Новое Имя', 'phone': '+7'}, format='json')
        self.assertEqual(r.data['full_name'], 'Новое Имя')
        r = self.client.patch('/api/auth/me/', {'current_password': 'wrong', 'new_password': 'newpass1'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.patch('/api/auth/me/', {'current_password': 'oldpass1', 'new_password': 'newpass1'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(User.objects.get(id=self.admin.id).check_password('newpass1'))

    def test_worker_cannot_manage_users(self):
        w = User.objects.create(username='w', role_worker=True)
        self.assertEqual(client_for(w).get('/api/users/').status_code, 403)
