from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Bucket, GlobalSettings, Notification, Payment, PaymentKind, Project,
    ProjectComment, ReviewStatus, Server, ServerRenewal, User,
)


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

    class Meta:
        model = Payment
        fields = ['id', 'project', 'kind', 'kind_display', 'amount', 'date',
                  'fund20_amount', 'fund5_amount', 'worker_amount', 'company_amount',
                  'created_at']
        read_only_fields = ['fund20_amount', 'fund5_amount', 'worker_amount', 'company_amount']


# --------------------------------------------------------------------------- #
#  Серверы
# --------------------------------------------------------------------------- #
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

    def create(self, validated_data):
        purchase = validated_data['purchase_date']
        validated_data['expiry_date'] = purchase + timedelta(days=validated_data['days'])
        return super().create(validated_data)


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


class ProjectSerializer(serializers.ModelSerializer):
    worker = serializers.PrimaryKeyRelatedField(queryset=User.with_role(User.Role.WORKER))
    worker_name = serializers.CharField(source='worker.full_name', read_only=True)
    worker_username = serializers.CharField(source='worker.username', read_only=True)
    reviewer_name = serializers.SerializerMethodField()
    review_status_display = serializers.CharField(source='get_review_status_display', read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    servers = ServerSerializer(many=True, read_only=True)
    totals = serializers.SerializerMethodField()
    deadline_status = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ['id', 'name', 'worker', 'worker_name', 'worker_username',
                  'reviewer', 'reviewer_name', 'review_status', 'review_status_display', 'comments',
                  'client_name', 'client_phone',
                  'has_price', 'price', 'worker_amount',
                  'fund1_rate', 'fund2_rate',
                  'has_monthly', 'monthly_amount', 'monthly_next_due',
                  'total_price', 'start_date', 'deadline_date', 'beta_date',
                  'finished_date', 'deadline_status',
                  'status', 'status_display', 'payments', 'servers', 'totals', 'created_at']
        read_only_fields = ['review_status', 'reviewer']

    def validate(self, attrs):
        validate_amounts(attrs)
        return validate_fund_rates(attrs, self.instance)

    def update(self, instance, validated_data):
        before = (instance.price, instance.worker_amount)
        project = super().update(instance, validated_data)
        # сумму проекта или рабочему поменяли — доля рабочего с уже полученных оплат пересчитывается
        if (project.price, project.worker_amount) != before:
            project.recalc_worker_shares()
        return project

    def get_reviewer_name(self, obj):
        return str(obj.reviewer) if obj.reviewer_id else None

    def get_deadline_status(self, obj):
        return obj.deadline_status()

    def get_totals(self, obj):
        agg = {'received': Decimal('0'), 'fund20': Decimal('0'), 'fund5': Decimal('0'),
               'worker': Decimal('0'), 'company': Decimal('0')}
        for p in obj.payments.all():
            agg['received'] += p.amount
            agg['fund20'] += p.fund20_amount
            agg['fund5'] += p.fund5_amount
            agg['worker'] += p.worker_amount
            agg['company'] += p.company_amount
        return agg


class WorkerProjectSerializer(ProjectSerializer):
    """Проект глазами рабочего: без денег компании и фондов, только его доля."""

    class Meta(ProjectSerializer.Meta):
        fields = ['id', 'name', 'worker', 'worker_name', 'reviewer', 'reviewer_name',
                  'review_status', 'review_status_display', 'comments',
                  'client_name', 'client_phone', 'worker_amount', 'has_price', 'has_monthly',
                  'start_date', 'deadline_date', 'beta_date', 'finished_date', 'deadline_status',
                  'status', 'status_display', 'servers', 'totals', 'created_at']

    def get_totals(self, obj):
        return {'worker': sum((p.worker_amount for p in obj.payments.all()), Decimal('0'))}


class TesterProjectSerializer(ProjectSerializer):
    """Проект глазами тестировщика: без денег и серверов."""

    class Meta(ProjectSerializer.Meta):
        fields = ['id', 'name', 'worker', 'worker_name', 'worker_username', 'reviewer', 'reviewer_name',
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


class ProjectCreateSerializer(serializers.ModelSerializer):
    """Создание проекта вместе с сервером."""
    worker = serializers.PrimaryKeyRelatedField(queryset=User.with_role(User.Role.WORKER))
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

    class Meta:
        model = Project
        fields = ['id', 'name', 'worker', 'client_name', 'client_phone',
                  'has_price', 'price', 'worker_amount',
                  'fund1_rate', 'fund2_rate',
                  'has_monthly', 'monthly_amount', 'start_date', 'deadline_date', 'beta_date',
                  'has_server', 'server_label', 'server_login', 'server_password',
                  'server_days', 'server_amount', 'server_paid_from', 'server_purchase_date']

    def validate(self, attrs):
        validate_amounts(attrs)
        return validate_fund_rates(attrs)

    def create(self, validated_data):
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

        project = Project.objects.create(**validated_data)

        if has_server and server_fields['days']:
            from django.utils import timezone
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


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'kind', 'title', 'message', 'is_read', 'created_at']


class GlobalSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalSettings
        fields = ['fund1_rate', 'fund1_name', 'fund2_rate', 'fund2_name']
