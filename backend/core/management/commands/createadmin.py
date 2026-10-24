"""
Создаёт супер-админа (для продакшна).

В отличие от `seed`, НЕ создаёт демо-данные. Идемпотентна:
если пользователь уже есть — возвращает ему роль админа и доступ,
пароль не меняет (для сброса — флаг --reset-password).

Логин/пароль берутся из аргументов или переменных окружения
DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD.
"""
import os

from django.core.management.base import BaseCommand

from core.models import User


class Command(BaseCommand):
    help = 'Создать супер-админа (или вернуть ему роль админа) без демо-данных'

    def add_arguments(self, parser):
        parser.add_argument('--username', default=os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin'))
        parser.add_argument('--password', default=os.environ.get('DJANGO_SUPERUSER_PASSWORD'))
        parser.add_argument('--full-name', default=os.environ.get('DJANGO_SUPERUSER_FULLNAME', 'Администратор'))
        parser.add_argument('--reset-password', action='store_true',
                            help='Поставить пароль из --password даже существующему админу')

    def handle(self, *args, **opts):
        username = opts['username']
        password = opts['password']
        if not password:
            self.stderr.write(self.style.ERROR(
                'Пароль не задан. Укажите --password или переменную DJANGO_SUPERUSER_PASSWORD.'))
            return

        user, created = User.objects.get_or_create(
            username=username,
            defaults=dict(role_admin=True, full_name=opts['full_name'],
                          is_staff=True, is_superuser=True),
        )
        # роль админа и доступ гарантируем всегда; другие роли (рабочий, тестировщик) не трогаем
        user.role_admin = True
        user.is_staff = True
        user.is_superuser = True
        # пароль и имя ставим только новому админу или по явной просьбе (--reset-password):
        # команда запускается при каждом деплое и не должна затирать смену пароля в профиле
        if created or opts['reset_password']:
            user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f'Супер-админ создан: {username}'))
        elif opts['reset_password']:
            self.stdout.write(self.style.SUCCESS(f'Пароль супер-админа {username} сброшен.'))
        else:
            self.stdout.write(f'Супер-админ {username} уже есть — пароль не меняю.')
