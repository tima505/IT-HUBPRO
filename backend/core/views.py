from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    Bucket, GlobalSettings, Notification, Payment, PaymentKind, Project,
    ProjectStatus, Server, ServerRenewal, ServerStatus, User, add_months,
)
from .serializers import (
    GlobalSettingsSerializer, MyTokenObtainPairSerializer, NotificationSerializer,
    PaymentSerializer, ProjectCreateSerializer, ProjectSerializer, ServerSerializer,
    UserSerializer, WorkerSerializer,
)
from .services import (
    finance_breakdown, finance_summary, generate_notifications, worker_earnings,
)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


# --------------------------------------------------------------------------- #
#  Рабочие
# --------------------------------------------------------------------------- #
class WorkerViewSet(viewsets.ModelViewSet):
    serializer_class = WorkerSerializer
    permission_classes = [IsAdmin]
    queryset = User.objects.filter(role=User.Role.WORKER).order_by('full_name')


# --------------------------------------------------------------------------- #
#  Проекты
# --------------------------------------------------------------------------- #
class ProjectViewSet(viewsets.ModelViewSet):
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'my', 'finish']:
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == 'create':
            return ProjectCreateSerializer
        return ProjectSerializer

    def get_queryset(self):
        qs = Project.objects.select_related('worker').prefetch_related('payments', 'servers')
        user = self.request.user
        if user.is_authenticated and not user.is_admin:
            qs = qs.filter(worker=user)
        return qs

    @action(detail=False, methods=['get'])
    def my(self, request):
        qs = Project.objects.filter(worker=request.user).prefetch_related('payments', 'servers')
        return Response(ProjectSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        """Добавить платёж (аванс/финал/ежемесячный) вручную."""
        project = self.get_object()
        kind = request.data.get('kind', PaymentKind.FINAL)
        amount = request.data.get('amount')
        if not amount:
            return Response({'detail': 'Укажите сумму'}, status=status.HTTP_400_BAD_REQUEST)
        payment = Payment.objects.create(project=project, kind=kind, amount=Decimal(str(amount)))
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Завершить проект: перевести статус в Завершён."""
        project = self.get_object()
        project.status = ProjectStatus.DONE
        project.save()
        return Response(ProjectSerializer(project).data)

    @action(detail=True, methods=['post'])
    def finish(self, request, pk=None):
        """Рабочий (или админ) отмечает фактическую дату сдачи проекта.

        Сравнивается с дедлайном → раньше / вовремя / позже.
        `clear: true` — снять отметку. Рабочий может менять только свой проект.
        """
        project = self.get_object()
        if not request.user.is_admin and project.worker_id != request.user.id:
            return Response({'detail': 'Нет доступа к этому проекту'},
                            status=status.HTTP_403_FORBIDDEN)
        if request.data.get('clear'):
            project.finished_date = None
        else:
            date_str = request.data.get('date')
            project.finished_date = date_str or timezone.localdate()
        project.save()
        return Response(ProjectSerializer(project).data)

    @action(detail=True, methods=['post'])
    def pay_monthly(self, request, pk=None):
        """Отметить ежемесячную оплату как полученную и сдвинуть срок на месяц вперёд."""
        project = self.get_object()
        if not project.has_monthly:
            return Response({'detail': 'Проект без ежемесячной оплаты'},
                            status=status.HTTP_400_BAD_REQUEST)
        amount = request.data.get('amount') or project.monthly_amount
        Payment.objects.create(
            project=project, kind=PaymentKind.MONTHLY, amount=Decimal(str(amount)))
        base = project.monthly_next_due or project.start_date
        project.monthly_next_due = add_months(base, 1)
        project.save()
        return Response(ProjectSerializer(project).data)

    @action(detail=False, methods=['get'])
    def due_monthly(self, request):
        """Проекты с приближающейся/наступившей ежемесячной оплатой (вкладка продления)."""
        today = timezone.localdate()
        qs = Project.objects.filter(
            has_monthly=True, status=ProjectStatus.ACTIVE)
        data = []
        for p in qs:
            if not p.monthly_next_due:
                continue
            item = ProjectSerializer(p).data
            item['days_left'] = (p.monthly_next_due - today).days
            data.append(item)
        data.sort(key=lambda x: x['days_left'])
        return Response(data)


# --------------------------------------------------------------------------- #
#  Серверы
# --------------------------------------------------------------------------- #
class ServerViewSet(viewsets.ModelViewSet):
    serializer_class = ServerSerializer
    permission_classes = [IsAdmin]
    queryset = Server.objects.select_related('project').prefetch_related('renewals')

    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        """Продлить сервер на N дней, оплата из выбранной корзины."""
        server = self.get_object()
        days = int(request.data.get('days', 0))
        amount = Decimal(str(request.data.get('amount', '0')))
        paid_from = request.data.get('paid_from', Bucket.COMPANY)
        if days <= 0:
            return Response({'detail': 'Укажите количество дней'}, status=status.HTTP_400_BAD_REQUEST)
        base = max(server.expiry_date, timezone.localdate())
        new_expiry = base + timedelta(days=days)
        ServerRenewal.objects.create(
            server=server, days=days, new_expiry=new_expiry, amount=amount, paid_from=paid_from)
        server.expiry_date = new_expiry
        server.status = ServerStatus.ACTIVE
        server.save()
        return Response(ServerSerializer(server).data)


# --------------------------------------------------------------------------- #
#  Финансы
# --------------------------------------------------------------------------- #
class FinanceView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        bucket = request.query_params.get('bucket')
        if bucket:
            return Response(finance_breakdown(bucket))
        return Response(finance_summary())


# --------------------------------------------------------------------------- #
#  Уведомления
# --------------------------------------------------------------------------- #
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        generate_notifications()  # пересчёт вех при опросе
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        generate_notifications()
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({'count': count})

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        n = self.get_object()
        n.is_read = True
        n.save()
        return Response({'ok': True})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
        return Response({'ok': True})


# --------------------------------------------------------------------------- #
#  Дашборд рабочего
# --------------------------------------------------------------------------- #
class WorkerDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        projects = Project.objects.filter(worker=user).prefetch_related('payments', 'servers')
        return Response({
            'user': UserSerializer(user).data,
            'total_earned': worker_earnings(user),
            'projects': ProjectSerializer(projects, many=True).data,
        })


# --------------------------------------------------------------------------- #
#  Настройки
# --------------------------------------------------------------------------- #
class SettingsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        settings = GlobalSettings.load()
        return Response(GlobalSettingsSerializer(settings).data)

    def put(self, request):
        settings = GlobalSettings.load()
        serializer = GlobalSettingsSerializer(settings, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
