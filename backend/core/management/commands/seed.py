from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    Bucket, GlobalSettings, Payment, PaymentKind, Project, ProjectStatus, Server, SubTask, Task,
    TaskPriority, TaskStatus, User, WorkerPayout,
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
        else:
            self.seed_projects(today, w1, w2)

        if Task.objects.exists():
            self.stdout.write('Демо-задачи уже созданы, пропускаю.')
        else:
            self.seed_tasks(today, admin, w1, w2)

    def seed_projects(self, today, w1, w2):
        D = lambda n: today + timedelta(days=n)

        def pay(project, amount, days_ago, note=''):
            Payment.objects.create(project=project, kind=PaymentKind.PAYMENT, amount=Decimal(amount),
                                   date=D(-days_ago), note=note)

        def payout(project, amount, days_ago, note=''):
            WorkerPayout.objects.create(project=project, worker=project.worker, amount=Decimal(amount),
                                        date=D(-days_ago), note=note)

        # Проект 1: 800 000, клиент платит частями, есть сервер
        p1 = Project.objects.create(
            name='Интернет-магазин «Sauda»', worker=w1,
            description='Каталог, корзина, оплата Kaspi, личный кабинет.',
            client_name='ТОО «Sauda Market»', client_phone='+7 701 111 22 33',
            price=Decimal('800000'), worker_amount=Decimal('140000'),
            start_date=D(-40), deadline_date=D(20), beta_date=D(5),
        )
        pay(p1, 100000, 40, 'Предоплата')
        pay(p1, 200000, 25, 'После макетов')
        pay(p1, 100000, 8)
        payout(p1, 50000, 20, 'Аванс')
        Server.objects.create(
            project=p1, label='VPS для Sauda', login='root', password='S3rv3r!',
            purchase_date=today - timedelta(days=353), days=365,
            expiry_date=today + timedelta(days=6),  # уведомление «7 дней» рядом
            amount=Decimal('45000'), paid_from=Bucket.COMPANY,
        )

        # Проект 2: обслуживание с ежемесячной оплатой, разовой цены нет
        p2 = Project.objects.create(
            name='CRM для клиники', worker=w2,
            client_name='Клиника «Densaulyq»', client_phone='+7 705 444 55 66',
            price=Decimal('0'), worker_amount=Decimal('60000'),
            has_monthly=True, monthly_amount=Decimal('150000'),
            start_date=D(-32), deadline_date=D(60), beta_date=D(15),
        )
        p2.monthly_next_due = D(3)  # уведомление «3 дня»
        p2.save()
        Payment.objects.create(project=p2, kind=PaymentKind.MONTHLY, amount=Decimal('150000'), date=D(-2))
        payout(p2, 60000, 1)

        # Проект 3: 1 000 000 + обслуживание, тот же клиент, что и проект 1
        p3 = Project.objects.create(
            name='ERP Система', worker=w1,
            client_name='ТОО «Sauda Market»', client_phone='+7 701 111 22 33',
            price=Decimal('1000000'), worker_amount=Decimal('150000'),
            has_monthly=True, monthly_amount=Decimal('50000'),
            start_date=D(-5), deadline_date=D(90), beta_date=D(40),
        )
        p3.monthly_next_due = D(25)
        p3.save()
        pay(p3, 200000, 5, 'Предоплата')

        # Проект 4: полностью оплачен и сдан
        p4 = Project.objects.create(
            name='Лендинг для автосервиса', worker=w2,
            client_name='ИП Ахметов', client_phone='+7 777 888 99 00',
            price=Decimal('250000'), worker_amount=Decimal('50000'),
            start_date=D(-60), deadline_date=D(-30), finished_date=D(-32),
            status=ProjectStatus.DONE,
        )
        pay(p4, 125000, 60, 'Предоплата 50%')
        pay(p4, 125000, 31, 'Остаток')
        payout(p4, 50000, 30)

        self.stdout.write(self.style.SUCCESS('Демо-проекты созданы.'))

    def seed_tasks(self, today, admin, w1, w2):
        projects = {p.worker_id: p for p in Project.objects.filter(status=ProjectStatus.ACTIVE).order_by('id')}
        D = lambda n: today + timedelta(days=n)
        demo = [
            # (исполнитель, заголовок, статус, приоритет, дедлайн, выполнена N дней назад, подзадачи [(текст, готово)])
            (w1, 'Каталог товаров: фильтры и сортировка', TaskStatus.IN_PROGRESS, TaskPriority.HIGH, D(2),
             None, [('Фильтр по цене', True), ('Фильтр по категориям', True), ('Сортировка', False)]),
            (w1, 'Интеграция оплаты Kaspi', TaskStatus.TODO, TaskPriority.HIGH, D(6), None,
             [('Получить ключи API', False), ('Webhook статуса оплаты', False)]),
            (w1, 'Адаптив карточки товара', TaskStatus.REVIEW, TaskPriority.MEDIUM, D(1), None, []),
            (w1, 'Настроить CI/CD для Sauda', TaskStatus.DONE, TaskPriority.MEDIUM, D(-3), 4, []),
            (w1, 'Страница «О компании»', TaskStatus.DONE, TaskPriority.LOW, D(-6), 5, []),
            (w1, 'Исправить баг корзины', TaskStatus.DONE, TaskPriority.HIGH, D(-8), 7, [('Воспроизвести', True), ('Фикс + тест', True)]),
            (w2, 'Запись пациентов: календарь', TaskStatus.IN_PROGRESS, TaskPriority.HIGH, D(4), None,
             [('Сетка расписания', True), ('Свободные слоты', False), ('SMS-напоминание', False)]),
            (w2, 'Экспорт отчётов в Excel', TaskStatus.TODO, TaskPriority.MEDIUM, D(-1), None, []),
            (w2, 'Роли врач / администратор', TaskStatus.DONE, TaskPriority.MEDIUM, D(-2), 1, []),
            (w2, 'Дизайн дашборда клиники', TaskStatus.DONE, TaskPriority.LOW, None, 3, []),
            (admin, 'Созвон с клиентом по ERP', TaskStatus.TODO, TaskPriority.MEDIUM, D(0), None, []),
        ]
        for pos, (user, title, st, prio, deadline, done_ago, subs) in enumerate(demo):
            task = Task.objects.create(
                title=title, assignee=user, created_by=admin, project=projects.get(user.id),
                status=st, priority=prio, deadline=deadline, position=pos)
            if done_ago is not None:
                done_at = timezone.now() - timedelta(days=done_ago)
                Task.objects.filter(pk=task.pk).update(completed_at=done_at,
                                                       created_at=done_at - timedelta(days=3))
            for i, (text, done) in enumerate(subs):
                SubTask.objects.create(task=task, title=text, is_done=done, position=i)

        self.stdout.write(self.style.SUCCESS('Демо-задачи созданы.'))
