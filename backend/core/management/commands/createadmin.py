"""
Создаёт/обновляет супер-админа с ролью admin (для продакшна).

В отличие от `seed`, НЕ создаёт демо-данные. Идемпотентна:
если пользователь уже есть — просто обновляет пароль и права.

Логин/пароль берутся из аргументов или переменных окружения
DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD.
"""
import os

from django.core.management.base import BaseCommand

from core.models import User


class Command(BaseCommand):
    help = 'Создать/обновить супер-админа (role=admin) без демо-данных'

    def add_arguments(self, parser):
        parser.add_argument('--username', default=os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin'))
        parser.add_argument('--password', default=os.environ.get('DJANGO_SUPERUSER_PASSWORD'))
        parser.add_argument('--full-name', default=os.environ.get('DJANGO_SUPERUSER_FULLNAME', 'Администратор'))

    def handle(self, *args, **opts):
        username = opts['username']
        password = opts['password']
        if not password:
            self.stderr.write(self.style.ERROR(
                'Пароль не задан. Укажите --password или переменную DJANGO_SUPERUSER_PASSWORD.'))
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults=dict(role=User.Role.ADMIN, full_name=opts['full_name'],
                          is_staff=True, is_superuser=True),
        )
        user.role = User.Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        if opts['full_name']:
            user.full_name = opts['full_name']
        user.set_password(password)
        user.save()

        verb = 'создан' if created else 'обновлён'
        self.stdout.write(self.style.SUCCESS(f'Супер-админ {verb}: {username}'))
