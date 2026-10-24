"""Роли совмещаются: вместо одного поля role — три отметки.

Каждый существующий пользователь получает ровно ту роль, что была у него раньше.
"""
from django.db import migrations, models

FIELDS = {'admin': 'role_admin', 'worker': 'role_worker', 'tester': 'role_tester'}


def role_to_flags(apps, schema_editor):
    User = apps.get_model('core', 'User')
    for old, field in FIELDS.items():
        User.objects.filter(role=old).update(**{field: True})


def flags_to_role(apps, schema_editor):
    # обратно: берём старшую из ролей (admin > tester > worker)
    User = apps.get_model('core', 'User')
    for user in User.objects.all():
        user.role = 'admin' if user.role_admin else ('tester' if user.role_tester and not user.role_worker else 'worker')
        user.save(update_fields=['role'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_any_tester_reviews'),
    ]

    operations = [
        migrations.AddField(model_name='user', name='role_admin',
                            field=models.BooleanField(default=False, verbose_name='Админ')),
        migrations.AddField(model_name='user', name='role_worker',
                            field=models.BooleanField(default=False, verbose_name='Рабочий')),
        migrations.AddField(model_name='user', name='role_tester',
                            field=models.BooleanField(default=False, verbose_name='Тестировщик')),
        migrations.RunPython(role_to_flags, flags_to_role),
        migrations.RemoveField(model_name='user', name='role'),
        migrations.AlterField(
            model_name='project', name='worker',
            field=models.ForeignKey(
                limit_choices_to={'role_worker': True}, on_delete=models.deletion.PROTECT,
                related_name='projects', to='core.user', verbose_name='Рабочий'),
        ),
    ]
