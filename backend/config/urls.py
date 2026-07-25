from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from core.views import (
    FinanceView, MyTokenObtainPairView, NotificationViewSet, ProjectViewSet,
    ServerViewSet, SettingsView, WorkerDashboardView, WorkerViewSet, me,
)

router = DefaultRouter()
router.register('workers', WorkerViewSet, basename='workers')
router.register('projects', ProjectViewSet, basename='projects')
router.register('servers', ServerViewSet, basename='servers')
router.register('notifications', NotificationViewSet, basename='notifications')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/login/', MyTokenObtainPairView.as_view()),
    path('api/auth/refresh/', TokenRefreshView.as_view()),
    path('api/auth/me/', me),
    path('api/finance/', FinanceView.as_view()),
    path('api/settings/', SettingsView.as_view()),
    path('api/worker/dashboard/', WorkerDashboardView.as_view()),
    path('api/', include(router.urls)),
]
