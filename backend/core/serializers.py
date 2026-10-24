from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Bucket, GlobalSettings, Notification, Payment, PaymentKind, Project,
    ProjectComment, ReviewStatus, Server, ServerRenewal, SubTask, Task, TaskStatus, User,
    WorkerPayout, money,
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
ROLE_LABELS = dict(User.Role.choices)


def roles_display(user):
    return ', '.join(ROLE_LABELS[r] for r in user.roles)


class RolesField(serializers.MultipleChoiceField):
    """Роли списком: ["admin", "worker", "tester"] — в постоянном порядке."""

    def __init__(self, **kwargs):
        super().__init__(choices=User.Role.choices, source='*', **kwargs)

    def to_representation(self, user):
        return user.roles

    def to_internal_value(self, data):
        return {'roles': list(super().to_internal_value(data))}


class UserSerializer(serializers.ModelSerializer):
    roles = RolesField(read_only=True)
    roles_display = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'phone', 'roles', 'roles_display']

    def get_roles_display(self, obj):
        return roles_display(obj)


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['roles'] = user.roles
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data


MIN_PASSWORD = 6


def check_password_length(value):
    if len(value) < MIN_PASSWORD:
        raise serializers.ValidationError(f'Пароль — минимум {MIN_PASSWORD} символов.')
    return value


class ProfileSerializer(serializers.ModelSerializer):
    """Свой профиль: имя, телефон и смена пароля (нужен текущий пароль)."""
    current_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    new_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['full_name', 'phone', 'current_password', 'new_password']

    def validate(self, attrs):
        new = attrs.get('new_password')
        if new:
            if len(new) < MIN_PASSWORD:
                raise serializers.ValidationError({'detail': f'Новый пароль — минимум {MIN_PASSWORD} символов.'})
            if not self.instance.check_password(attrs.get('current_password') or ''):
                raise serializers.ValidationError({'detail': 'Текущий пароль указан неверно.'})
        return attrs

    def update(self, instance, validated_data):
        new = validated_data.pop('new_password', None)
        validated_data.pop('current_password', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if new:
            instance.set_password(new)
        instance.save()
        return instance


class UserManageSerializer(serializers.ModelSerializer):
    """Управление пользователями (админ). Роли совмещаются в любом сочетании."""
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    roles = RolesField()
    roles_display = serializers.SerializerMethodField()
    projects_count = serializers.SerializerMethodField()
    reviewed_count = serializers.SerializerMethodField()
    total_earned = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'full_name', 'phone', 'roles', 'roles_display', 'password',
                  'projects_count', 'reviewed_count', 'total_earned']

    def get_roles_display(self, obj):
        return roles_display(obj)

    def get_projects_count(self, obj):
        return obj.projects.count()

    def get_reviewed_count(self, obj):
        return obj.reviewed_projects.count()

    def get_total_earned(self, obj):
        from .services import worker_earnings
        return worker_earnings(obj)

    def validate_password(self, value):
        return check_password_length(value) if value else value

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': ['Укажите пароль.']})
        roles = attrs.get('roles')
        if roles is None and self.instance is None:
            raise serializers.ValidationError({'detail': 'Выберите хотя бы одну роль.'})
        if roles is not None:
            if not roles:
                raise serializers.ValidationError({'detail': 'Выберите хотя бы одну роль.'})
            user = self.instance
            if user is not None:
                if user.is_worker and User.Role.WORKER not in roles and user.projects.exists():
                    raise serializers.ValidationError(
                        {'detail': 'У пользователя есть проекты — роль «Рабочий» снять нельзя.'})
                request = self.context.get('request')
                if request and user.id == request.user.id and User.Role.ADMIN not in roles:
                    raise serializers.ValidationError({'detail': 'Нельзя снять роль админа с самого себя.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        roles = validated_data.pop('roles')
        user = User(**validated_data)
        user.set_roles(roles)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        roles = validated_data.pop('roles', None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if roles is not None:
            instance.set_roles(roles)
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
def validate_amounts(attrs):
    """Сумма проекта и сумма рабочему необязательны, но не могут быть отрицательными."""
    for field in ('price', 'worker_amount', 'monthly_amount'):
        value = attrs.get(field)
        if value is not None and value < 0:
            raise serializers.ValidationError({'detail': 'Сумма не может быть отрицательной.'})


def validate_fund_rates(attrs, instance=None):
    """Ставки фондов проекта: каждая 0–100, в сумме не больше 100."""
    total = Decimal('0')
    for field in ('fund1_rate', 'fund2_rate'):
        rate = attrs.get(field, getattr(instance, field, None))
        if rate is None:
            continue
        if rate < 0 or rate > 100:
            raise serializers.ValidationError({'detail': 'Процент фонда должен быть от 0 до 100.'})
        total += rate
    if total > 100:
        raise serializers.ValidationError({'detail': 'Проценты фондов в сумме не могут быть больше 100.'})
    return attrs


class CommentSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)
    author_name = serializers.SerializerMethodField()
    author_role = serializers.SerializerMethodField()

    class Meta:
        model = ProjectComment
        fields = ['id', 'kind', 'kind_display', 'text', 'author', 'author_name', 'author_role', 'created_at']

    def get_author_name(self, obj):
        return str(obj.author) if obj.author_id else 'Удалённый пользователь'

    def get_author_role(self, obj):
        # в каком качестве человек писал: рабочий своего проекта, тестировщик или админ
        author = obj.author
        if author is None:
            return None
        if author.id == obj.project.worker_id:
            return User.Role.WORKER
        if author.is_tester:
            return User.Role.TESTER
        return User.Role.ADMIN if author.is_admin else None


MONEY = dict(max_digits=14, decimal_places=2, read_only=True)


class ProjectSerializer(serializers.ModelSerializer):
    """Проект целиком — для админа."""
    worker = serializers.PrimaryKeyRelatedField(queryset=User.with_role(User.Role.WORKER), label='Рабочий')
    worker_name = serializers.CharField(source='worker.full_name', read_only=True)
    worker_username = serializers.CharField(source='worker.username', read_only=True)
    reviewer_name = serializers.SerializerMethodField()
    review_status_display = serializers.CharField(source='get_review_status_display', read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    payouts = WorkerPayoutSerializer(many=True, read_only=True)
    servers = ServerSerializer(many=True, read_only=True)
    paid = serializers.DecimalField(**MONEY)
    debt = serializers.DecimalField(**MONEY)
    worker_paid = serializers.DecimalField(**MONEY)
    worker_debt = serializers.DecimalField(**MONEY)
    paid_percent = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    deadline_status = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'worker', 'worker_name', 'worker_username',
                  'reviewer', 'reviewer_name', 'review_status', 'review_status_display', 'comments',
                  'client_name', 'client_phone',
                  'price', 'paid', 'debt', 'paid_percent',
                  'worker_amount', 'worker_paid', 'worker_debt',
                  'fund1_rate', 'fund2_rate',
                  'has_monthly', 'monthly_amount', 'monthly_next_due',
                  'total_price', 'start_date', 'deadline_date', 'beta_date',
                  'finished_date', 'deadline_status',
                  'status', 'status_display', 'payments', 'payouts', 'servers', 'totals', 'created_at']
        read_only_fields = ['review_status', 'reviewer']
        extra_kwargs = {'price': {'min_value': Decimal('0')}, 'worker_amount': {'min_value': Decimal('0')},
                        'monthly_amount': {'min_value': Decimal('0')}}

    def validate(self, attrs):
        validate_amounts(attrs)
        validate_fund_rates(attrs, self.instance)
        validate_project_dates(attrs, self.instance)
        inst = self.instance
        if inst:
            if 'price' in attrs and attrs['price'] < inst.paid:
                raise field_error('price', f'Клиент уже оплатил {_tenge(inst.paid)} — цена не может быть меньше.')
            if 'worker_amount' in attrs and attrs['worker_amount'] < inst.worker_paid:
                raise field_error('worker_amount',
                                  f'Рабочему уже выплачено {_tenge(inst.worker_paid)} — сумма не может быть меньше.')
        return attrs

    def get_reviewer_name(self, obj):
        return str(obj.reviewer) if obj.reviewer_id else None

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


class WorkerProjectSerializer(ProjectSerializer):
    """Проект глазами рабочего: без денег клиента и компании, только его сумма и выплаты."""

    class Meta(ProjectSerializer.Meta):
        fields = ['id', 'name', 'description', 'worker', 'worker_name', 'reviewer', 'reviewer_name',
                  'review_status', 'review_status_display', 'comments',
                  'client_name', 'client_phone', 'worker_amount', 'worker_paid', 'worker_debt', 'payouts',
                  'has_monthly', 'start_date', 'deadline_date', 'beta_date', 'finished_date', 'deadline_status',
                  'status', 'status_display', 'servers', 'created_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for server in data.get('servers', []):  # пароли и деньги серверов — только админу
            for key in ('password', 'amount', 'paid_from', 'paid_from_display', 'renewals'):
                server.pop(key, None)
        return data


class TesterProjectSerializer(ProjectSerializer):
    """Проект глазами тестировщика: без денег и серверов."""

    class Meta(ProjectSerializer.Meta):
        fields = ['id', 'name', 'description', 'worker', 'worker_name', 'worker_username', 'reviewer', 'reviewer_name',
                  'review_status', 'review_status_display', 'comments',
                  'start_date', 'deadline_date', 'beta_date', 'finished_date', 'deadline_status',
                  'status', 'status_display', 'created_at']


def project_serializer_for(user, project):
    """Как показать проект человеку: админ — целиком, свой проект — как рабочему,
    чужой (для тестировщика) — без денег."""
    if user.is_admin:
        return ProjectSerializer
    if project.worker_id == user.id:
        return WorkerProjectSerializer
    return TesterProjectSerializer


def serialize_projects(user, projects):
    return [project_serializer_for(user, p)(p).data for p in projects]


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
            share = prepayment_share(prepayment, bucket, attrs.get('fund1_rate'), attrs.get('fund2_rate'))
            check_balance(bucket, amount, refund=share, field='server_amount')
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


def prepayment_share(amount, bucket, rate1=None, rate2=None) -> Decimal:
    """Сколько из предоплаты попадёт в корзину (по ставкам проекта или общим)."""
    if not amount:
        return Decimal('0')
    settings = GlobalSettings.load()
    rate1 = settings.fund1_rate if rate1 is None else rate1
    rate2 = settings.fund2_rate if rate2 is None else rate2
    f1 = money(amount * rate1 / Decimal('100'))
    f2 = money(amount * rate2 / Decimal('100'))
    return {Bucket.FUND20: f1, Bucket.FUND5: f2, Bucket.COMPANY: amount - f1 - f2}[bucket]


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
