from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Bucket, GlobalSettings, Notification, Payment, PaymentKind, Project,
    Server, ServerRenewal, SubTask, Task, TaskStatus, User, WorkerPayout, money,
)


def field_error(field: str, message: str):
    """Ошибка по полю + готовое сообщение `detail` для показа пользователю."""
    return serializers.ValidationError({field: [message], 'detail': message})


def bucket_name(bucket: str) -> str:
    """Название «корзины» с учётом пользовательских названий фондов."""
    settings = GlobalSettings.load()
    return {
        Bucket.FUND20: settings.fund1_name,
        Bucket.FUND5: settings.fund2_name,
    }.get(bucket, Bucket(bucket).label if bucket in Bucket.values else bucket)


def check_balance(bucket: str, amount, refund=Decimal('0'), field='amount'):
    """Не даём уйти в минус: расход из корзины не больше её баланса.

    `refund` — сумма, которая вернётся в корзину (при редактировании старого расхода).
    """
    from .services import bucket_balance
    if not amount or amount <= 0:
        return
    available = bucket_balance(bucket) + refund
    if amount > available:
        tenge = lambda v: f'{v:,.0f} ₸'.replace(',', ' ')
        raise field_error(field, (
            f'Недостаточно средств в «{bucket_name(bucket)}»: '
            f'доступно {tenge(available)}, нужно {tenge(amount)}.'
        ))


def validate_project_dates(attrs, instance=None):
    """Дедлайн и бета не раньше старта; бета не позже дедлайна."""
    def get(name):
        if name in attrs:
            return attrs[name]
        return getattr(instance, name, None) if instance else None

    start, deadline, beta = get('start_date'), get('deadline_date'), get('beta_date')
    if start and deadline and deadline < start:
        raise field_error('deadline_date', 'Дедлайн не может быть раньше даты начала.')
    if beta and start and beta < start:
        raise field_error('beta_date', 'Показ беты не может быть раньше даты начала.')
    if beta and deadline and beta > deadline:
        raise field_error('beta_date', 'Показ беты не может быть позже дедлайна.')


# --------------------------------------------------------------------------- #
#  Пользователи / аутентификация
# --------------------------------------------------------------------------- #
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'phone', 'role']


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data


class WorkerSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    projects_count = serializers.SerializerMethodField()
    total_earned = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'phone', 'password',
                  'projects_count', 'total_earned']

    def get_projects_count(self, obj):
        return obj.projects.count()

    def get_total_earned(self, obj):
        from .services import worker_earnings
        return worker_earnings(obj)

    def create(self, validated_data):
        password = validated_data.pop('password', None) or 'worker12345'
        user = User(role=User.Role.WORKER, **validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


# --------------------------------------------------------------------------- #
#  Платежи
# --------------------------------------------------------------------------- #
class PaymentSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ['id', 'project', 'kind', 'kind_display', 'amount', 'date', 'note',
                  'fund20_amount', 'fund5_amount', 'company_amount', 'created_by_name', 'created_at']
        read_only_fields = fields

    def get_created_by_name(self, obj):
        return str(obj.created_by) if obj.created_by else None


class WorkerPayoutSerializer(serializers.ModelSerializer):
    worker_name = serializers.SerializerMethodField()
    paid_from_display = serializers.CharField(source='get_paid_from_display', read_only=True)

    class Meta:
        model = WorkerPayout
        fields = ['id', 'project', 'worker', 'worker_name', 'amount', 'date', 'paid_from',
                  'paid_from_display', 'note', 'created_at']
        read_only_fields = fields

    def get_worker_name(self, obj):
        return str(obj.worker)


def validate_not_future(value):
    if value and value > timezone.localdate():
        raise serializers.ValidationError('Дата не может быть в будущем.')
    return value


def _tenge(v) -> str:
    return f'{v:,.0f} ₸'.replace(',', ' ')


class AddPaymentSerializer(serializers.Serializer):
    """Оплата клиента в счёт цены проекта — любая часть, но не больше остатка долга."""
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'), label='Сумма')
    date = serializers.DateField(required=False, allow_null=True, label='Дата оплаты',
                                 validators=[validate_not_future])
    note = serializers.CharField(required=False, allow_blank=True, max_length=255, label='Комментарий')

    def validate_amount(self, amount):
        project = self.context['project']
        if project.debt <= 0:
            raise serializers.ValidationError('Проект уже полностью оплачен.')
        if amount > project.debt:
            raise serializers.ValidationError(
                f'Остаток долга по проекту {_tenge(project.debt)} — нельзя принять больше.')
        return amount


class WorkerPayoutCreateSerializer(serializers.Serializer):
    """Выплата рабочему: не больше, чем мы ему ещё должны, и не больше, чем есть в корзине."""
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'), label='Сумма')
    date = serializers.DateField(required=False, allow_null=True, label='Дата выплаты',
                                 validators=[validate_not_future])
    paid_from = serializers.ChoiceField(choices=Bucket.choices, default=Bucket.COMPANY, label='Оплачено из')
    note = serializers.CharField(required=False, allow_blank=True, max_length=255, label='Комментарий')

    def validate_amount(self, amount):
        project = self.context['project']
        if project.worker_debt <= 0:
            raise serializers.ValidationError('Рабочему по этому проекту уже всё выплачено.')
        if amount > project.worker_debt:
            raise serializers.ValidationError(
                f'Рабочему осталось выплатить {_tenge(project.worker_debt)} — нельзя выплатить больше. '
                f'Если договорились о большей сумме, измените «Должны рабочему» в проекте.')
        return amount

    def validate(self, attrs):
        check_balance(attrs['paid_from'], attrs['amount'])
        return attrs


class MonthlyPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'),
                                      required=False, allow_null=True, label='Сумма')

    def validate(self, attrs):
        amount = attrs.get('amount') or self.context['project'].monthly_amount
        if not amount or amount <= 0:
            raise field_error('amount', 'Не указана сумма ежемесячной оплаты — задайте её в проекте или передайте сумму.')
        attrs['amount'] = money(amount)
        return attrs


class FinishSerializer(serializers.Serializer):
    clear = serializers.BooleanField(default=False)
    date = serializers.DateField(required=False, allow_null=True, label='Дата сдачи')

    def validate_date(self, value):
        project = self.context['project']
        if value and value < project.start_date:
            raise serializers.ValidationError('Дата сдачи не может быть раньше даты начала проекта.')
        if value and value > timezone.localdate():
            raise serializers.ValidationError('Дата сдачи не может быть в будущем.')
        return value


class RenewSerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, label='Количество дней')
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0'),
                                      default=Decimal('0'), label='Стоимость')
    paid_from = serializers.ChoiceField(choices=Bucket.choices, default=Bucket.COMPANY, label='Оплачено из')

    def validate(self, attrs):
        check_balance(attrs['paid_from'], attrs['amount'])
        return attrs


class ServerRenewalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServerRenewal
        fields = ['id', 'server', 'date', 'days', 'new_expiry', 'amount', 'paid_from', 'created_at']
        read_only_fields = ['new_expiry']


class ServerSerializer(serializers.ModelSerializer):
    days_left = serializers.IntegerField(read_only=True)
    paid_from_display = serializers.CharField(source='get_paid_from_display', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True, default=None)
    renewals = ServerRenewalSerializer(many=True, read_only=True)
    # логин/пароль можно указать позже — не блокируем покупку
    login = serializers.CharField(required=False, allow_blank=True, default='')
    password = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = Server
        fields = ['id', 'label', 'login', 'password', 'project', 'project_name',
                  'purchase_date', 'days', 'expiry_date', 'amount', 'paid_from',
                  'paid_from_display', 'status', 'days_left', 'renewals', 'created_at']
        read_only_fields = ['expiry_date', 'status']
        extra_kwargs = {
            'days': {'min_value': 1},
            'amount': {'min_value': Decimal('0')},
        }

    def validate(self, attrs):
        inst = self.instance
        bucket = attrs.get('paid_from', inst.paid_from if inst else Bucket.COMPANY)
        amount = attrs.get('amount', inst.amount if inst else Decimal('0'))
        # при редактировании старая сумма возвращается в ту же корзину
        refund = inst.amount if inst and inst.paid_from == bucket else Decimal('0')
        if not inst or 'amount' in attrs or 'paid_from' in attrs:
            check_balance(bucket, amount, refund)
        return attrs

    def create(self, validated_data):
        purchase = validated_data['purchase_date']
        validated_data['expiry_date'] = purchase + timedelta(days=validated_data['days'])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # изменили дату покупки/срок — сдвигаем окончание на ту же разницу
        # (уже сделанные продления сохраняются)
        old_end = instance.purchase_date + timedelta(days=instance.days)
        new_end = (validated_data.get('purchase_date', instance.purchase_date)
                   + timedelta(days=validated_data.get('days', instance.days)))
        if new_end != old_end:
            validated_data['expiry_date'] = instance.expiry_date + (new_end - old_end)
        return super().update(instance, validated_data)


# --------------------------------------------------------------------------- #
#  Проекты
# --------------------------------------------------------------------------- #
PROJECT_MONEY_FIELDS = ['price', 'worker_amount']


class ProjectSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.full_name', read_only=True)
    worker_username = serializers.CharField(source='worker.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    payouts = WorkerPayoutSerializer(many=True, read_only=True)
    servers = ServerSerializer(many=True, read_only=True)
    paid = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    debt = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    worker_paid = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    worker_debt = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    paid_percent = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    deadline_status = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'worker', 'worker_name', 'worker_username',
                  'client_name', 'client_phone',
                  'price', 'paid', 'debt', 'paid_percent',
                  'worker_amount', 'worker_paid', 'worker_debt',
                  'has_monthly', 'monthly_amount', 'monthly_next_due',
                  'start_date', 'deadline_date', 'beta_date',
                  'finished_date', 'deadline_status',
                  'status', 'status_display', 'payments', 'payouts', 'servers', 'totals', 'created_at']
        extra_kwargs = {'price': {'min_value': Decimal('0')}, 'worker_amount': {'min_value': Decimal('0')},
                        'monthly_amount': {'min_value': Decimal('0')}}

    def validate(self, attrs):
        validate_project_dates(attrs, self.instance)
        inst = self.instance
        if inst:
            if 'price' in attrs and attrs['price'] < inst.paid:
                raise field_error('price', f'Клиент уже оплатил {_tenge(inst.paid)} — цена не может быть меньше.')
            if 'worker_amount' in attrs and attrs['worker_amount'] < inst.worker_paid:
                raise field_error('worker_amount',
                                  f'Рабочему уже выплачено {_tenge(inst.worker_paid)} — сумма не может быть меньше.')
        return attrs

    # что рабочий видит о своём проекте: без денег клиента и компании
    WORKER_HIDDEN = ['client_phone', 'price', 'paid', 'debt', 'paid_percent', 'payments', 'totals', 'monthly_amount']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        if request and not request.user.is_admin:
            for key in self.WORKER_HIDDEN:
                data.pop(key, None)
            for server in data.get('servers', []):
                server.pop('password', None)
                server.pop('amount', None)
                server.pop('paid_from', None)
                server.pop('paid_from_display', None)
                server.pop('renewals', None)
        return data

    def get_paid_percent(self, obj):
        if obj.price <= 0:
            return None
        return min(100, round(obj.paid * 100 / obj.price))

    def get_deadline_status(self, obj):
        return obj.deadline_status()

    def get_totals(self, obj):
        agg = {'received': Decimal('0'), 'fund20': Decimal('0'), 'fund5': Decimal('0'),
               'company': Decimal('0'), 'monthly': Decimal('0')}
        for p in obj.payments.all():
            agg['received'] += p.amount
            agg['fund20'] += p.fund20_amount
            agg['fund5'] += p.fund5_amount
            agg['company'] += p.company_amount
            if p.kind == PaymentKind.MONTHLY:
                agg['monthly'] += p.amount
        agg['worker'] = obj.worker_paid
        return agg


class ProjectCreateSerializer(ProjectSerializer):
    """Создание проекта: можно сразу записать предоплату клиента и купленный сервер."""
    prepayment = serializers.DecimalField(max_digits=14, decimal_places=2, write_only=True, required=False,
                                          allow_null=True, min_value=Decimal('0'), label='Предоплата')
    prepayment_date = serializers.DateField(write_only=True, required=False, allow_null=True,
                                            validators=[validate_not_future], label='Дата предоплаты')
    # сервер
    has_server = serializers.BooleanField(write_only=True, required=False, default=False)
    server_label = serializers.CharField(write_only=True, required=False, allow_blank=True)
    server_login = serializers.CharField(write_only=True, required=False, allow_blank=True)
    server_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    server_days = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    server_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, write_only=True, required=False, allow_null=True)
    server_paid_from = serializers.ChoiceField(
        choices=Bucket.choices, write_only=True, required=False, allow_blank=True)
    server_purchase_date = serializers.DateField(write_only=True, required=False, allow_null=True)

    class Meta(ProjectSerializer.Meta):
        fields = ProjectSerializer.Meta.fields + [
            'prepayment', 'prepayment_date',
            'has_server', 'server_label', 'server_login', 'server_password',
            'server_days', 'server_amount', 'server_paid_from', 'server_purchase_date']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        price = attrs.get('price') or Decimal('0')
        if price <= 0 and not attrs.get('has_monthly'):
            raise field_error('price', 'Укажите цену проекта.')
        prepayment = attrs.get('prepayment') or Decimal('0')
        if prepayment > price:
            raise field_error('prepayment', 'Предоплата не может быть больше цены проекта.')
        if attrs.get('has_monthly') and not attrs.get('monthly_amount'):
            raise field_error('monthly_amount', 'Укажите сумму ежемесячной оплаты.')
        if attrs.get('has_server'):
            if not attrs.get('server_days') or attrs['server_days'] <= 0:
                raise field_error('server_days', 'Укажите срок сервера (дней).')
            amount = attrs.get('server_amount') or Decimal('0')
            if amount < 0:
                raise field_error('server_amount', 'Стоимость сервера не может быть отрицательной.')
            bucket = attrs.get('server_paid_from') or Bucket.COMPANY
            # сервер можно оплатить и из предоплаты, которая придёт вместе с проектом
            check_balance(bucket, amount, refund=prepayment_share(prepayment, bucket), field='server_amount')
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        prepayment = validated_data.pop('prepayment', None)
        prepayment_date = validated_data.pop('prepayment_date', None)
        has_server = validated_data.pop('has_server', False)
        server_fields = {
            'label': validated_data.pop('server_label', ''),
            'login': validated_data.pop('server_login', ''),
            'password': validated_data.pop('server_password', ''),
            'days': validated_data.pop('server_days', None),
            'amount': validated_data.pop('server_amount', None) or Decimal('0'),
            'paid_from': validated_data.pop('server_paid_from', '') or Bucket.COMPANY,
            'purchase_date': validated_data.pop('server_purchase_date', None),
        }

        with transaction.atomic():
            project = Project.objects.create(**validated_data)
            if prepayment:
                Payment.objects.create(project=project, kind=PaymentKind.PAYMENT, amount=prepayment,
                                       date=prepayment_date or timezone.localdate(),
                                       note='Предоплата', created_by=user)
            if has_server and server_fields['days']:
                purchase = server_fields['purchase_date'] or timezone.localdate()
                Server.objects.create(
                    project=project,
                    label=server_fields['label'] or f'Сервер: {project.name}',
                    login=server_fields['login'],
                    password=server_fields['password'],
                    purchase_date=purchase,
                    days=server_fields['days'],
                    expiry_date=purchase + timedelta(days=server_fields['days']),
                    amount=server_fields['amount'],
                    paid_from=server_fields['paid_from'],
                )
        return project

    def to_representation(self, instance):
        return ProjectSerializer(instance, context=self.context).data


def prepayment_share(amount, bucket) -> Decimal:
    """Сколько из предоплаты попадёт в корзину (по текущим ставкам фондов)."""
    if not amount:
        return Decimal('0')
    probe = Payment(amount=amount)
    probe.distribute()
    return {Bucket.FUND20: probe.fund20_amount, Bucket.FUND5: probe.fund5_amount,
            Bucket.COMPANY: probe.company_amount}[bucket]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'kind', 'title', 'message', 'is_read', 'created_at']


class GlobalSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalSettings
        fields = ['fund1_rate', 'fund1_name', 'fund2_rate', 'fund2_name']

    def validate(self, attrs):
        r1 = attrs.get('fund1_rate', self.instance.fund1_rate if self.instance else 0)
        r2 = attrs.get('fund2_rate', self.instance.fund2_rate if self.instance else 0)
        if r1 + r2 > 100:
            raise field_error('fund2_rate', f'Сумма ставок фондов не может превышать 100% (сейчас {r1 + r2}%).')
        return attrs


# --------------------------------------------------------------------------- #
#  Задачи
# --------------------------------------------------------------------------- #
class SubTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubTask
        fields = ['id', 'task', 'title', 'is_done', 'position', 'done_at']
        read_only_fields = ['done_at']

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Введите название подзадачи.')
        return value

    def validate_task(self, task):
        user = self.context['request'].user
        if not user.is_admin and task.assignee_id != user.id:
            raise serializers.ValidationError('Нет доступа к этой задаче.')
        return task


class TaskSerializer(serializers.ModelSerializer):
    assignee_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True, default=None)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    deadline_state = serializers.SerializerMethodField()
    subtasks = SubTaskSerializer(many=True, read_only=True)
    subtasks_total = serializers.SerializerMethodField()
    subtasks_done = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ['id', 'title', 'description', 'assignee', 'assignee_name', 'created_by', 'created_by_name',
                  'project', 'project_name', 'status', 'status_display', 'priority', 'priority_display',
                  'deadline', 'deadline_state', 'position', 'completed_at',
                  'subtasks', 'subtasks_total', 'subtasks_done', 'created_at', 'updated_at']
        read_only_fields = ['created_by', 'completed_at', 'position']
        extra_kwargs = {'assignee': {'required': False}}

    def get_assignee_name(self, obj):
        return str(obj.assignee)

    def get_created_by_name(self, obj):
        return str(obj.created_by) if obj.created_by else None

    def get_deadline_state(self, obj):
        return obj.deadline_state()

    def get_subtasks_total(self, obj):
        return len(obj.subtasks.all())

    def get_subtasks_done(self, obj):
        return sum(1 for st in obj.subtasks.all() if st.is_done)

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Введите название задачи.')
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.is_admin:
            # рабочий ведёт только свои задачи и только по своим проектам
            assignee = attrs.get('assignee')
            if assignee and assignee.id != user.id:
                raise field_error('assignee', 'Рабочий может назначать задачи только себе.')
            project = attrs.get('project')
            if project and project.worker_id != user.id:
                raise field_error('project', 'Можно привязать задачу только к своему проекту.')
        elif not self.instance and not attrs.get('assignee'):
            raise field_error('assignee', 'Выберите исполнителя.')
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data.setdefault('assignee', user)
        validated_data['created_by'] = user
        # новая задача — в конец колонки
        last = Task.objects.filter(status=validated_data.get('status', TaskStatus.TODO)).order_by('-position').first()
        validated_data['position'] = (last.position + 1) if last else 0
        return super().create(validated_data)
