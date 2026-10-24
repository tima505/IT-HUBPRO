"""Тестировщики больше не прикрепляются к проектам и рабочим.

Project.tester становится Project.reviewer — тот, кто принял или вернул проект.
Уже записанный тестировщик сохраняется только там, где проверка состоялась
(проект принят или возвращён); у остальных проектов поле очищается.
Связь рабочий → тестировщик (User.tester) удаляется.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def keep_only_real_reviewers(apps, schema_editor):
    Project = apps.get_model('core', 'Project')
    Project.objects.exclude(review_status__in=['accepted', 'returned']).update(reviewer=None)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_tester_review'),
    ]

    operations = [
        migrations.RenameField(model_name='project', old_name='tester', new_name='reviewer'),
        migrations.AlterField(
            model_name='project',
            name='reviewer',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='reviewed_projects', to=settings.AUTH_USER_MODEL, verbose_name='Проверил'),
        ),
        migrations.RunPython(keep_only_real_reviewers, migrations.RunPython.noop),
        migrations.RemoveField(model_name='user', name='tester'),
    ]
