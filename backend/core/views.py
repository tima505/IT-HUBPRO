from datetime import timedelta
from decimal import Decimal

from django.db.models import ProtectedError, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    Bucket, GlobalSettings, Notification, Payment, PaymentKind, Project,
    ProjectComment, ProjectStatus, ReviewStatus, Server, ServerRenewal,
    ServerStatus, User, add_months,
)
from .serializers import (
    GlobalSettingsSerializer, MyTokenObtainPairSerializer, NotificationSerializer,
    PaymentSerializer, ProfileSerializer, ProjectCreateSerializer, ProjectSerializer,
    ServerSerializer, UserManageSerializer, UserSerializer, WorkerProjectSerializer,
    project_serializer_for, serialize_projects,
)
from .services import (
    _admins, _testers, activity_log, finance_breakdown, finance_summary, generate_notifications,
    notify_review, worker_earnings,
)


def bad_request(detail):
    return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin)


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def me(request):
    """Свой профиль: посмотреть и изменить имя, телефон, пароль."""
    if request.method == 'PATCH':
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
    return Response(UserSerializer(request.user).data)


# --------------------------------------------------------------------------- #
#  Пользователи: админы, рабочие, тестировщики
# --------------------------------------------------------------------------- #
class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserManageSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = User.objects.order_by('full_name', 'username')
        role = self.request.query_params.get('role')
        if role in User.ROLE_FIELDS:
            qs = qs.filter(**{User.ROLE_FIELDS[role]: True})
        return qs

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.id == request.user.id:
            return bad_request('Нельзя удалить самого себя.')
        try:
            user.delete()
        except ProtectedError:
            return bad_request('За этим рабочим закреплены проекты — удалить его нельзя.')
        return Response(status=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
#  Проекты
# --------------------------------------------------------------------------- #
# новые платежи: оплата за проект (сколько угодно частями) или ежемесячная
NEW_PAYMENT_KINDS = [PaymentKind.PAYMENT, PaymentKind.MONTHLY]


class ProjectViewSet(viewsets.ModelViewSet):
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'my', 'finish', 'submit', 'review', 'comment']:
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_serializer_class(self):
        if self.action == 'create':
            return ProjectCreateSerializer
        return ProjectSerializer  # для правок (только админ); чтение — через serialize_projects

    def list(self, request, *args, **kwargs):
        return Response(serialize_projects(request.user, self.get_queryset()))

    def retrieve(self, request, *args, **kwargs):
        project = self.get_object()
        return Response(project_serializer_for(request.user, project)(project).data)

    def get_queryset(self):
        qs = Project.objects.select_related('worker', 'reviewer').prefetch_related(
            'payments', 'servers', 'comments__author')
        user = self.request.user
        if not user.is_authenticated or user.is_admin:
            return qs
        # роли совмещаются: свои проекты (рабочий) + все неотменённые (тестировщик)
        own = Q(worker=user) if user.is_worker else Q(pk__in=[])
        if user.is_tester:
            return qs.filter(own | ~Q(status=ProjectStatus.CANCELLED))
        return qs.filter(own)

    def _respond(self, project):
        """Свежий проект в том виде, в каком его видит текущий пользователь."""
        project = self.get_queryset().get(pk=project.pk)
        return Response(project_serializer_for(self.request.user, project)(project).data)

    @action(detail=False, methods=['get'])
    def my(self, request):
        qs = self.get_queryset().filter(worker=request.user)
        return Response(WorkerProjectSerializer(qs, many=True).data)

    # ----- проверка тестировщиком ------------------------------------------ #
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Рабочий отправляет проект на проверку и пишет, что сделано."""
        project = self.get_object()
        user = request.user
        if not user.is_admin and project.worker_id != user.id:
            return Response({'detail': 'Отправить на проверку может только рабочий проекта.'},
                            status=status.HTTP_403_FORBIDDEN)
        if project.status != ProjectStatus.ACTIVE:
            return bad_request('Проект не в работе.')
        if project.review_status == ReviewStatus.REVIEW:
            return bad_request('Проект уже на проверке.')
        if project.review_status == ReviewStatus.ACCEPTED:
            return bad_request('Проект уже принят тестировщиком.')
        text = (request.data.get('text') or '').strip()
        if not text:
            return bad_request('Напишите, что сделано, — это увидит тестировщик.')

        project.review_status = ReviewStatus.REVIEW
        project.finished_date = timezone.localdate()  # сдача считается с момента отправки
        project.save()
        comment = ProjectComment.objects.create(
            project=project, author=user, kind=ProjectComment.Kind.SUBMIT, text=text)
        notify_review(comment, [*_testers(), *_admins()], 'Проект на проверку',
                      f'{project.worker} отправил проект «{project.name}» на проверку.')
        return self._respond(project)

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Любой тестировщик (или админ) принимает проект или возвращает его.

        Решает тот, кто успел первым: второй получит «проект уже не на проверке».
        """
        project = self.get_object()
        user = request.user
        if not (user.is_admin or user.is_tester):
            return Response({'detail': 'Проверять проекты могут только тестировщики.'},
                            status=status.HTTP_403_FORBIDDEN)
        if project.worker_id == user.id and not user.is_admin:
            return Response({'detail': 'Свой проект проверять нельзя — его проверит другой тестировщик.'},
                            status=status.HTTP_403_FORBIDDEN)
        decision = request.data.get('decision')
        text = (request.data.get('text') or '').strip()

        if decision == 'accept':
            changes = {'review_status': ReviewStatus.ACCEPTED}
            kind, title = ProjectComment.Kind.ACCEPT, 'Проект принят'
            message = f'{user} принял проект «{project.name}».'
        elif decision == 'return':
            if not text:
                return bad_request('Опишите недостатки — без этого вернуть проект нельзя.')
            changes = {'review_status': ReviewStatus.RETURNED, 'finished_date': None}  # сдача не засчитана
            kind, title = ProjectComment.Kind.RETURN, 'Проект возвращён'
            message = f'{user} вернул проект «{project.name}» на доработку.'
        else:
            return bad_request('Укажите решение: принять или вернуть.')

        # условное обновление: если два тестировщика нажмут одновременно, сработает только первый
        updated = Project.objects.filter(pk=project.pk, review_status=ReviewStatus.REVIEW).update(
            reviewer=user, **changes)
        if not updated:
            project.refresh_from_db()
            if project.review_status == ReviewStatus.ACCEPTED:
                return bad_request(f'Проект уже принят ({project.reviewer or "другой тестировщик"}).')
            return bad_request('Проект сейчас не на проверке.')
        comment = ProjectComment.objects.create(project=project, author=user, kind=kind, text=text)
        notify_review(comment, [project.worker, *_admins()], title, message)
        return self._respond(project)

    @action(detail=True, methods=['post'])
    def comment(self, request, pk=None):
        """Обычный комментарий в переписке по проекту."""
        project = self.get_object()  # queryset уже отсекает чужие проекты
        text = (request.data.get('text') or '').strip()
        if not text:
            return bad_request('Комментарий пустой.')
        comment = ProjectComment.objects.create(project=project, author=request.user, text=text)
        # пишет рабочий — узнают тестировщики (тот, кто проверял, или все); пишут ему — узнаёт рабочий
        if request.user.id == project.worker_id:
            recipients = [project.reviewer] if project.reviewer_id else list(_testers())
        else:
            recipients = [project.worker]
        notify_review(comment, recipients, 'Новый комментарий',
                      f'{request.user} написал в проекте «{project.name}»: {text[:120]}')
        return self._respond(project)

    # ----- платежи --------------------------------------------------------- #
    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        """Принять оплату по проекту — частями, сколько угодно раз."""
        project = self.get_object()
        kind = request.data.get('kind', PaymentKind.PAYMENT)
        amount = request.data.get('amount')
        if kind not in NEW_PAYMENT_KINDS:
            return bad_request('Неизвестный тип платежа.')
        try:
            amount = Decimal(str(amount))
        except Exception:
            return bad_request('Укажите сумму.')
        if amount <= 0:
            return bad_request('Сумма должна быть больше нуля.')
        payment = Payment.objects.create(project=project, kind=kind, amount=amount)
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
        if not request.user.is_admin:
            return bad_request('Сдача проекта идёт через проверку — отправьте проект тестировщикам.')
        if request.data.get('clear'):
            project.finished_date = None
        else:
            date_str = request.data.get('date')
            project.finished_date = date_str or timezone.localdate()
        project.save()
        return self._respond(project)

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
#  История
# --------------------------------------------------------------------------- #
class HistoryView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(activity_log())


# --------------------------------------------------------------------------- #
#  Уведомления
# --------------------------------------------------------------------------- #
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]  # у рабочих и тестировщиков свои уведомления

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
        projects = Project.objects.filter(worker=user).select_related('worker', 'reviewer').prefetch_related(
            'payments', 'servers', 'comments__author')
        return Response({
            'user': UserSerializer(user).data,
            'total_earned': worker_earnings(user),
            'projects': WorkerProjectSerializer(projects, many=True).data,
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
