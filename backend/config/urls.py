from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from core.views import (
    DebtsView, FinanceView, HistoryView, MyTokenObtainPairView, NotificationViewSet, ProjectViewSet,
    ServerViewSet, SettingsView, SubTaskViewSet, TaskViewSet, UserViewSet, WorkerDashboardView, me,
)

router = DefaultRouter()
router.register('users', UserViewSet, basename='users')
router.register('projects', ProjectViewSet, basename='projects')
router.register('servers', ServerViewSet, basename='servers')
router.register('notifications', NotificationViewSet, basename='notifications')
router.register('tasks', TaskViewSet, basename='tasks')
router.register('subtasks', SubTaskViewSet, basename='subtasks')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/login/', MyTokenObtainPairView.as_view()),
    path('api/auth/refresh/', TokenRefreshView.as_view()),
    path('api/auth/me/', me),
    path('api/finance/', FinanceView.as_view()),
    path('api/debts/', DebtsView.as_view()),
    path('api/history/', HistoryView.as_view()),
    path('api/settings/', SettingsView.as_view()),
    path('api/worker/dashboard/', WorkerDashboardView.as_view()),
    path('api/', include(router.urls)),
]
