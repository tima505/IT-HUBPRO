"""Одна сумма проекта вместо этапов «старт / бета / сдача» + данные клиента.

Перенос старых проектов:
  price         = старт + бета + сдача (если хоть одна была указана)
  worker_amount = рабочему за бету + за сдачу (если больше нуля)
Уже проведённые платежи не пересчитываются — их распределение остаётся как было.
"""
from decimal import Decimal

from django.db import migrations, models


def stages_to_price(apps, schema_editor):
    Project = apps.get_model('core', 'Project')
    for p in Project.objects.all():
        parts = [p.start_amount, p.beta_amount, p.final_amount]
        if any(x is not None for x in parts):
            p.price = sum((x or Decimal('0') for x in parts), Decimal('0'))
        worker = (p.worker_beta_amount or Decimal('0')) + (p.worker_final_amount or Decimal('0'))
        p.worker_amount = worker if worker > 0 else None
        p.save(update_fields=['price', 'worker_amount'])


def price_to_stages(apps, schema_editor):
    # обратно: вся сумма уходит в «сдачу», сумма рабочему — в «за сдачу»
    Project = apps.get_model('core', 'Project')
    for p in Project.objects.all():
        p.final_amount = p.price
        p.worker_final_amount = p.worker_amount or Decimal('0')
        p.save(update_fields=['final_amount', 'worker_final_amount'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_multiple_roles'),
    ]

    operations = [
        migrations.AddField(model_name='project', name='client_name',
                            field=models.CharField(blank=True, max_length=150, verbose_name='Клиент')),
        migrations.AddField(model_name='project', name='client_phone',
                            field=models.CharField(blank=True, max_length=30, verbose_name='Телефон клиента')),
        migrations.AddField(model_name='project', name='price',
                            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True,
                                                      verbose_name='Сумма проекта')),
        migrations.AddField(model_name='project', name='worker_amount',
                            field=models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True,
                                                      verbose_name='Сумма рабочему')),
        migrations.RunPython(stages_to_price, price_to_stages),
        migrations.RenameField(model_name='project', old_name='has_stages', new_name='has_price'),
        migrations.AlterField(model_name='project', name='has_price',
                              field=models.BooleanField(default=True, verbose_name='Оплата за проект')),
        migrations.RemoveField(model_name='project', name='start_amount'),
        migrations.RemoveField(model_name='project', name='beta_amount'),
        migrations.RemoveField(model_name='project', name='final_amount'),
        migrations.RemoveField(model_name='project', name='worker_beta_amount'),
        migrations.RemoveField(model_name='project', name='worker_final_amount'),
        migrations.AlterField(
            model_name='payment', name='kind',
            field=models.CharField(choices=[
                ('payment', 'Оплата'), ('monthly', 'Ежемесячная оплата'),
                ('start', 'Старт'), ('beta', 'Бета'), ('final', 'Сдача')], max_length=10),
        ),
    ]
