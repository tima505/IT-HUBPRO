from datetime import date
from decimal import Decimal

from django.test import TestCase

from .models import Bucket, GlobalSettings, Notification, Payment, PaymentKind, Project, User
from .services import fund_balances


class FinanceLogicTests(TestCase):
    def setUp(self):
        self.worker = User.objects.create(username='w', role_worker=True)
        # Убедимся что настройки по умолчанию (20% / 5%)
        GlobalSettings.load()

    def _project(self, price=None, worker=None, has_monthly=False):
        return Project.objects.create(
            name='P', worker=self.worker, has_monthly=has_monthly,
            price=Decimal(str(price)) if price is not None else None,
            worker_amount=Decimal(str(worker)) if worker is not None else None,
            start_date=date(2026, 1, 1), deadline_date=date(2026, 2, 1),
        )

    def _pay(self, project, amount, kind=PaymentKind.PAYMENT):
        return Payment.objects.create(project=project, kind=kind, amount=Decimal(str(amount)))

    def test_payment_without_worker_amount(self):
        """Оплата 100000, сумма рабочему не указана: 20000 / 5000 / 0 / 75000."""
        pay = self._pay(self._project(price=500000), 100000)
        self.assertEqual(pay.fund20_amount, Decimal('20000.00'))
        self.assertEqual(pay.fund5_amount, Decimal('5000.00'))
        self.assertEqual(pay.worker_amount, Decimal('0.00'))
        self.assertEqual(pay.company_amount, Decimal('75000.00'))

    def test_worker_share_is_proportional(self):
        """Цена 400000, рабочему 80000. Оплата 100000 (25%) → рабочему 20000 (25%)."""
        pay = self._pay(self._project(price=400000, worker=80000), 100000)
        self.assertEqual(pay.worker_amount, Decimal('20000.00'))
        self.assertEqual(pay.company_amount, Decimal('55000.00'))
        total = pay.fund20_amount + pay.fund5_amount + pay.worker_amount + pay.company_amount
        self.assertEqual(total, Decimal('100000.00'))

    def test_last_payment_closes_worker_amount(self):
        """Три оплаты по 100000 на цену 300000 — рабочий получает ровно 100000, без копеечных хвостов."""
        p = self._project(price=300000, worker=100000)
        shares = [self._pay(p, 100000).worker_amount for _ in range(3)]
        self.assertEqual(shares, [Decimal('33333.33'), Decimal('33333.33'), Decimal('33333.34')])
        self.assertEqual(sum(shares), Decimal('100000.00'))
        # переплата сверх цены рабочему больше не начисляет
        self.assertEqual(self._pay(p, 50000).worker_amount, Decimal('0.00'))

    def test_worker_amount_without_price(self):
        """Цена не указана: рабочему идёт остаток после фондов, пока не наберётся его сумма."""
        p = self._project(worker=50000)
        first = self._pay(p, 40000)                 # после фондов остаётся 30000
        self.assertEqual(first.worker_amount, Decimal('30000.00'))
        self.assertEqual(first.company_amount, Decimal('0.00'))
        second = self._pay(p, 100000)               # добирается до 50000
        self.assertEqual(second.worker_amount, Decimal('20000.00'))

    def test_price_and_worker_amount_can_change_later(self):
        """Сумму поменяли внутри проекта — новые оплаты считаются по новым суммам."""
        p = self._project(price=200000)
        self.assertEqual(self._pay(p, 100000).worker_amount, Decimal('0.00'))
        p.price, p.worker_amount = Decimal('300000'), Decimal('60000')
        p.save()
        p.recalc_worker_shares()
        # первая оплата (треть цены) пересчиталась: 20000; вторая — ещё 20000
        self.assertEqual(self._pay(p, 100000).worker_amount, Decimal('20000.00'))
        self.assertEqual(sum(x.worker_amount for x in p.payments.all()), Decimal('40000.00'))

    def test_worker_amount_set_after_full_payment(self):
        """Клиент оплатил всё, сумму рабочему указали потом — его доля начисляется с уже полученных денег."""
        admin = User.objects.create(username='adm', role_admin=True)
        p = self._project(price=120000)
        pay = self._pay(p, 120000)
        self.assertEqual(pay.worker_amount, Decimal('0.00'))
        r = client_for(admin).patch(f'/api/projects/{p.id}/', {'worker_amount': 15000}, format='json')
        self.assertEqual(r.data['totals']['worker'], Decimal('15000.00'))
        pay.refresh_from_db()
        # фонды прежние, рабочий забрал своё из доли компании
        self.assertEqual(pay.fund20_amount + pay.fund5_amount, Decimal('30000.00'))
        self.assertEqual(pay.worker_amount, Decimal('15000.00'))
        self.assertEqual(pay.company_amount, Decimal('75000.00'))
        # сумму рабочему уменьшили — пересчиталось и в обратную сторону
        r = client_for(admin).patch(f'/api/projects/{p.id}/', {'worker_amount': 5000}, format='json')
        self.assertEqual(r.data['totals']['worker'], Decimal('5000.00'))
        self.assertEqual(r.data['totals']['company'], Decimal('85000.00'))

    def test_monthly_no_worker(self):
        """Ежемесячная оплата: доли рабочего нет, только 20% / 5% / компания."""
        p = self._project(price=100000, worker=50000, has_monthly=True)
        pay = self._pay(p, 150000, PaymentKind.MONTHLY)
        self.assertEqual(pay.fund20_amount, Decimal('30000.00'))
        self.assertEqual(pay.fund5_amount, Decimal('7500.00'))
        self.assertEqual(pay.worker_amount, Decimal('0.00'))
        self.assertEqual(pay.company_amount, Decimal('112500.00'))

    def test_history_is_not_recalculated(self):
        """Старый платёж при пересохранении не пересчитывается по новым правилам."""
        p = self._project(price=100000, worker=50000)
        pay = self._pay(p, 100000)
        p.worker_amount = Decimal('0')
        p.save()
        pay.save()
        pay.refresh_from_db()
        self.assertEqual(pay.worker_amount, Decimal('50000.00'))

    def test_custom_fund_rates(self):
        """Проверяем что из настроек берутся нестандартные ставки."""
        settings = GlobalSettings.load()
        settings.fund1_rate = Decimal('10.00')
        settings.fund2_rate = Decimal('10.00')
        settings.save()
        pay = self._pay(self._project(), 100000)
        self.assertEqual(pay.fund20_amount, Decimal('10000.00'))
        self.assertEqual(pay.fund5_amount, Decimal('10000.00'))
        self.assertEqual(pay.company_amount, Decimal('80000.00'))

    def test_project_fund_rates_override_settings(self):
        """Ставки проекта важнее настроек: 30% / 10% со 100000 → 30000 / 10000 / 60000."""
        p = self._project()
        p.fund1_rate = Decimal('30.00')
        p.fund2_rate = Decimal('10.00')
        p.save()
        pay = self._pay(p, 100000)
        self.assertEqual(pay.fund20_amount, Decimal('30000.00'))
        self.assertEqual(pay.fund5_amount, Decimal('10000.00'))
        self.assertEqual(pay.company_amount, Decimal('60000.00'))

    def test_project_api(self):
        """Создание через API: клиент, одна сумма, пустая сумма рабочему, свои ставки."""
        admin = User.objects.create(username='a', role_admin=True)
        client = client_for(admin)
        body = {'name': 'API', 'worker': self.worker.id, 'has_price': True,
                'start_date': '2026-01-01', 'deadline_date': '2026-02-01'}

        r = client.post('/api/projects/', {**body, 'client_name': 'ТОО Ромашка', 'client_phone': '+7 700 123 45 67',
                                           'price': 500000, 'worker_amount': None}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['client_phone'], '+7 700 123 45 67')
        self.assertEqual(Decimal(r.data['total_price']), Decimal('500000'))
        self.assertIsNone(r.data['worker_amount'])
        # сумму рабочему добавили позже, цену изменили
        pid = r.data['id']
        r = client.patch(f'/api/projects/{pid}/', {'worker_amount': 90000, 'price': 600000}, format='json')
        self.assertEqual(Decimal(r.data['worker_amount']), Decimal('90000'))
        self.assertEqual(client.patch(f'/api/projects/{pid}/', {'price': -1}, format='json').status_code, 400)

        r = client.post('/api/projects/', {**body, 'fund1_rate': 30, 'fund2_rate': 0}, format='json')
        self.assertEqual(Decimal(r.data['fund1_rate']), Decimal('30'))
        r = client.post('/api/projects/', {**body, 'fund1_rate': 80, 'fund2_rate': 30}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_payments_in_parts(self):
        admin = User.objects.create(username='a2', role_admin=True)
        client = client_for(admin)
        p = self._project(price=300000, worker=60000)
        url = f'/api/projects/{p.id}/add_payment/'
        # оплату можно принимать частями сколько угодно раз
        for _ in range(2):
            self.assertEqual(client.post(url, {'amount': 100000}, format='json').status_code, 201)
        self.assertEqual(client.post(url, {'kind': 'monthly', 'amount': 1000}, format='json').status_code, 201)
        # старые этапы и мусор не принимаются
        self.assertEqual(client.post(url, {'kind': 'beta', 'amount': 1000}, format='json').status_code, 400)
        self.assertEqual(client.post(url, {'amount': 0}, format='json').status_code, 400)
        r = client.get(f'/api/projects/{p.id}/')
        self.assertEqual(r.data['totals']['worker'], Decimal('40000.00'))

    def test_fund_balances_aggregate(self):
        p = self._project()
        self._pay(p, 100000)
        self._pay(p, 100000)
        balances = fund_balances()
        self.assertEqual(balances[Bucket.FUND20]['balance'], Decimal('40000.00'))
        self.assertEqual(balances[Bucket.FUND5]['balance'], Decimal('10000.00'))
        self.assertEqual(balances[Bucket.COMPANY]['balance'], Decimal('150000.00'))


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
        for field in ('totals', 'payments', 'servers', 'price', 'worker_amount', 'client_phone'):
            self.assertNotIn(field, t)
        w = self.as_worker.get(self.url).data
        self.assertNotIn('payments', w)
        self.assertNotIn('price', w)
        self.assertEqual(w['client_phone'], '+7 777 000 00 00')
        self.assertEqual(list(w['totals'].keys()), ['worker'])
        self.assertEqual(w['totals']['worker'], Decimal('5000.00'))

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

    def test_project_optional_amounts(self):
        r = self.as_admin.post('/api/projects/', {
            'name': 'Пустые суммы', 'worker': self.worker.id, 'has_price': True,
            'price': None, 'worker_amount': None,
            'start_date': '2026-01-01', 'deadline_date': '2026-02-01',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIsNone(r.data['price'])
        self.assertIsNone(r.data['reviewer'])
        self.assertEqual(r.data['review_status'], 'none')


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
        self.assertIn('totals', data['Мой'])            # свой — как рабочему, со своей долей
        self.assertNotIn('totals', data['Чужой'])       # чужой — как тестировщику, без денег
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
