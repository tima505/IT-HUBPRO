from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    Bucket, GlobalSettings, Notification, Payment, PaymentKind, Project,
    ProjectStatus, WorkerPayout, Server, ServerRenewal, ServerStatus, SubTask, Task, TaskStatus, User,
)
from .exceptions import validate_or_raise
from .serializers import (
    AddPaymentSerializer, FinishSerializer, WorkerPayoutCreateSerializer, GlobalSettingsSerializer, MonthlyPaymentSerializer,
    MyTokenObtainPairSerializer, NotificationSerializer, PaymentSerializer,
    ProjectCreateSerializer, ProjectSerializer, RenewSerializer, ServerSerializer,
    SubTaskSerializer, TaskSerializer, UserSerializer, WorkerSerializer,
)
from .services import (
    debts_summary, finance_breakdown, finance_summary, fund_balances, generate_notifications, generate_task_notifications,
    notify_task_assigned, refresh_server_statuses, task_report, worker_earnings,
)


def _bad_request(detail):
    return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)


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

    def destroy(self, request, *args, **kwargs):
        worker = self.get_object()
        count = worker.projects.count()
        if count:
            return _bad_request(
                f'Нельзя удалить рабочего: за ним {count} проект(ов). Сначала переназначьте их.')
        return super().destroy(request, *args, **kwargs)


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
        qs = Project.objects.select_related('worker').prefetch_related(
            'payments', 'payouts__worker', 'servers__renewals', 'servers__project')
        user = self.request.user
        if user.is_authenticated and not user.is_admin:
            qs = qs.filter(worker=user)
        return qs

    @action(detail=False, methods=['get'])
    def my(self, request):
        qs = self.get_queryset().filter(worker=request.user)
        return Response(ProjectSerializer(qs, many=True, context=self.get_serializer_context()).data)

    def _project_response(self, project, code=status.HTTP_200_OK):
        project = self.get_queryset().get(pk=project.pk)  # свежие оплаты/выплаты
        return Response(ProjectSerializer(project, context=self.get_serializer_context()).data, status=code)

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        """Оплата клиента: любая часть цены, остаток долга уменьшается."""
        with transaction.atomic():
            project = self.get_object()
            ser = AddPaymentSerializer(data=request.data, context={'project': project})
            validate_or_raise(ser)
            data = ser.validated_data
            Payment.objects.create(project=project, kind=PaymentKind.PAYMENT, amount=data['amount'],
                                   date=data.get('date') or timezone.localdate(),
                                   note=data.get('note', ''), created_by=request.user)
        return self._project_response(project, status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def pay_worker(self, request, pk=None):
        """Выплата рабочему: долг перед рабочим уменьшается, деньги списываются из корзины."""
        with transaction.atomic():
            project = self.get_object()
            ser = WorkerPayoutCreateSerializer(data=request.data, context={'project': project})
            validate_or_raise(ser)
            data = ser.validated_data
            WorkerPayout.objects.create(project=project, worker=project.worker, amount=data['amount'],
                                        date=data.get('date') or timezone.localdate(),
                                        paid_from=data['paid_from'], note=data.get('note', ''),
                                        created_by=request.user)
        return self._project_response(project, status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path=r'payments/(?P<payment_id>\d+)')
    def delete_payment(self, request, pk=None, payment_id=None):
        """Удалить ошибочно внесённую оплату (если её деньги ещё не потрачены)."""
        project = self.get_object()
        payment = project.payments.filter(pk=payment_id).first()
        if not payment:
            return Response({'detail': 'Оплата не найдена.'}, status=status.HTTP_404_NOT_FOUND)
        balances = fund_balances()
        shares = {Bucket.FUND20: payment.fund20_amount, Bucket.FUND5: payment.fund5_amount,
                  Bucket.COMPANY: payment.company_amount}
        for bucket, share in shares.items():
            if balances[bucket]['balance'] - share < 0:
                return _bad_request('Деньги из этой оплаты уже потрачены (серверы или выплаты рабочим) — '
                                    'удалить её нельзя, иначе баланс уйдёт в минус.')
        payment.delete()
        return self._project_response(project)

    @action(detail=True, methods=['delete'], url_path=r'payouts/(?P<payout_id>\d+)')
    def delete_payout(self, request, pk=None, payout_id=None):
        """Удалить ошибочно внесённую выплату рабочему (деньги возвращаются в корзину)."""
        project = self.get_object()
        deleted, _ = project.payouts.filter(pk=payout_id).delete()
        if not deleted:
            return Response({'detail': 'Выплата не найдена.'}, status=status.HTTP_404_NOT_FOUND)
        return self._project_response(project)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Завершить проект: перевести статус в Завершён.

        Если рабочий ещё не отметил сдачу — датой сдачи считается сегодня.
        """
        project = self.get_object()
        project.status = ProjectStatus.DONE
        if not project.finished_date:
            project.finished_date = timezone.localdate()
        project.save()
        return self._project_response(project)

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
        ser = FinishSerializer(data=request.data, context={'project': project})
        validate_or_raise(ser)
        if not request.user.is_admin and project.status != ProjectStatus.ACTIVE:
            return _bad_request(f'Проект уже в статусе «{project.get_status_display()}» — '
                                f'изменить отметку сдачи может только администратор.')
        if ser.validated_data['clear']:
            project.finished_date = None
        else:
            project.finished_date = ser.validated_data.get('date') or timezone.localdate()
        project.save()
        return self._project_response(project)

    @action(detail=True, methods=['post'])
    def pay_monthly(self, request, pk=None):
        """Отметить ежемесячную оплату как полученную и сдвинуть срок на месяц вперёд."""
        project = self.get_object()
        if not project.has_monthly:
            return Response({'detail': 'Проект без ежемесячной оплаты'},
                            status=status.HTTP_400_BAD_REQUEST)
        ser = MonthlyPaymentSerializer(data=request.data, context={'project': project})
        validate_or_raise(ser)
        Payment.objects.create(
            project=project, kind=PaymentKind.MONTHLY, amount=ser.validated_data['amount'])
        project.monthly_next_due = project.next_monthly_due()
        project.save()
        return self._project_response(project)

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

    def get_queryset(self):
        refresh_server_statuses()
        return super().get_queryset()

    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        """Продлить сервер на N дней, оплата из выбранной корзины."""
        server = self.get_object()
        ser = RenewSerializer(data=request.data)
        validate_or_raise(ser)
        days, amount, paid_from = (ser.validated_data[k] for k in ('days', 'amount', 'paid_from'))
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
class DebtsView(APIView):
    """Кто сколько должен: клиенты компании и компания рабочим."""
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(debts_summary())


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
def _refresh_notifications(user):
    """Пересчёт вех при опросе колокольчика: админу — серверы/оплаты, всем — свои задачи."""
    if user.is_admin:
        generate_notifications()
    generate_task_notifications(user)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.action == 'list':
            _refresh_notifications(self.request.user)
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        _refresh_notifications(request.user)
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
#  Задачи (канбан)
# --------------------------------------------------------------------------- #
class TaskViewSet(viewsets.ModelViewSet):
    """Админ видит и ведёт все задачи, рабочий — только свои.

    Фильтры списка: ?assignee=<id>|me, ?project=<id>, ?status=, ?q=<поиск>.
    """
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Task.objects.select_related('assignee', 'created_by', 'project').prefetch_related('subtasks')
        if not user.is_admin:
            qs = qs.filter(assignee=user)
        params = self.request.query_params
        assignee = params.get('assignee')
        if assignee == 'me':
            qs = qs.filter(assignee=user)
        elif assignee and assignee.isdigit():
            qs = qs.filter(assignee_id=assignee)
        if params.get('project', '').isdigit():
            qs = qs.filter(project_id=params['project'])
        if params.get('status') in TaskStatus.values:
            qs = qs.filter(status=params['status'])
        if params.get('q'):
            qs = qs.filter(Q(title__icontains=params['q']) | Q(description__icontains=params['q']))
        return qs

    def perform_create(self, serializer):
        task = serializer.save()
        notify_task_assigned(task, self.request.user)

    def perform_update(self, serializer):
        old_assignee = serializer.instance.assignee_id
        task = serializer.save()
        if task.assignee_id != old_assignee:
            notify_task_assigned(task, self.request.user)

    def destroy(self, request, *args, **kwargs):
        task = self.get_object()
        if not request.user.is_admin and task.created_by_id != request.user.id:
            return Response({'detail': 'Удалить задачу, поставленную администратором, может только он.'},
                            status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def assignees(self, request):
        """Кому можно назначить задачу: админу — вся команда, рабочему — только себе."""
        user = request.user
        qs = User.objects.filter(is_active=True) if user.is_admin else User.objects.filter(pk=user.pk)
        return Response(UserSerializer(qs.order_by('role', 'full_name', 'username'), many=True).data)

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        """Перетаскивание на доске: {status, ids:[...]} — новый порядок колонки целиком."""
        new_status = request.data.get('status')
        ids = request.data.get('ids')
        if new_status not in TaskStatus.values:
            return _bad_request('Неизвестная колонка.')
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            return _bad_request('Передайте список задач.')
        tasks = {t.id: t for t in self.get_queryset().filter(id__in=ids)}
        if len(tasks) != len(set(ids)):
            return _bad_request('Часть задач не найдена или недоступна.')
        with transaction.atomic():
            for position, task_id in enumerate(ids):
                task = tasks[task_id]
                if task.status != new_status or task.position != position:
                    task.status, task.position = new_status, position
                    task.save(update_fields=['status', 'position', 'completed_at', 'updated_at'])
        return Response(TaskSerializer(self.get_queryset().filter(id__in=ids), many=True,
                                       context=self.get_serializer_context()).data)

    @action(detail=False, methods=['get'])
    def report(self, request):
        """Аналитика за месяц: ?month=YYYY-MM (по умолчанию текущий)."""
        today = timezone.localdate()
        try:
            year, month = map(int, request.query_params.get('month', f'{today:%Y-%m}').split('-'))
            if not 1 <= month <= 12 or not 2000 <= year <= 2100:
                raise ValueError
        except ValueError:
            return _bad_request('Месяц укажите в формате ГГГГ-ММ.')
        user = request.user
        if user.is_admin:
            # вся команда: рабочие + админы, у которых есть задачи
            users = User.objects.filter(Q(role=User.Role.WORKER) | Q(tasks__isnull=False)).distinct()
        else:
            users = User.objects.filter(pk=user.pk)
        return Response(task_report(year, month, users.order_by('full_name', 'username')))


class SubTaskViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin,
                     mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = SubTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = SubTask.objects.select_related('task')
        if not self.request.user.is_admin:
            qs = qs.filter(task__assignee=self.request.user)
        return qs

    def perform_create(self, serializer):
        task = serializer.validated_data['task']
        last = task.subtasks.order_by('-position').first()
        serializer.save(position=(last.position + 1) if last else 0)


# --------------------------------------------------------------------------- #
#  Дашборд рабочего
# --------------------------------------------------------------------------- #
class WorkerDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        projects = Project.objects.filter(worker=user).prefetch_related('payments', 'payouts__worker', 'servers')
        data = ProjectSerializer(projects, many=True, context={'request': request}).data
        return Response({
            'user': UserSerializer(user).data,
            'total_earned': worker_earnings(user),
            'total_owed': sum((p.worker_debt for p in projects), 0),
            'projects': data,
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
