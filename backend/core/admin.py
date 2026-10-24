from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Notification, Payment, Project, ProjectComment, Server, ServerRenewal, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Штатная админка пользователя.

    ВАЖНО: без неё (при обычном admin.site.register(User)) пароль в форме
    сохранялся бы открытым текстом без хеширования, и вход не работал бы.
    """
    list_display = ('username', 'full_name', 'role_admin', 'role_worker', 'role_tester', 'is_active')
    list_filter = ('role_admin', 'role_worker', 'role_tester', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'full_name', 'phone')
    ordering = ('username',)

    fieldsets = BaseUserAdmin.fieldsets + (
        ('IT HubPro', {'fields': ('role_admin', 'role_worker', 'role_tester', 'full_name', 'phone')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('IT HubPro', {'fields': ('role_admin', 'role_worker', 'role_tester', 'full_name', 'phone')}),
    )


admin.site.register(Project)
admin.site.register(Payment)
admin.site.register(ProjectComment)
admin.site.register(Server)
admin.site.register(ServerRenewal)
admin.site.register(Notification)
