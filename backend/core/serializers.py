from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Bucket, GlobalSettings, Notification, Payment, PaymentKind, Project,
    Server, ServerRenewal, User,
)


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
class ProjectSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.full_name', read_only=True)
    worker_username = serializers.CharField(source='worker.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    servers = ServerSerializer(many=True, read_only=True)
    totals = serializers.SerializerMethodField()
    deadline_status = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ['id', 'name', 'worker', 'worker_name', 'worker_username',
                  'worker_beta_amount', 'worker_final_amount',
                  'has_stages', 'start_amount', 'beta_amount', 'final_amount',
                  'has_monthly', 'monthly_amount', 'monthly_next_due',
                  'total_price', 'start_date', 'deadline_date', 'beta_date',
                  'finished_date', 'deadline_status',
                  'status', 'status_display', 'payments', 'servers', 'totals', 'created_at']

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


class ProjectCreateSerializer(serializers.ModelSerializer):
    """Создание проекта вместе с сервером."""
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
        fields = ['id', 'name', 'worker', 'worker_beta_amount', 'worker_final_amount',
                  'has_stages', 'start_amount', 'beta_amount', 'final_amount',
                  'has_monthly', 'monthly_amount', 'start_date', 'deadline_date', 'beta_date',
                  'has_server', 'server_label', 'server_login', 'server_password',
                  'server_days', 'server_amount', 'server_paid_from', 'server_purchase_date']

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
