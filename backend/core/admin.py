from django.contrib import admin

from .models import Notification, Payment, Project, Server, ServerRenewal, User

admin.site.register(User)
admin.site.register(Project)
admin.site.register(Payment)
admin.site.register(Server)
admin.site.register(ServerRenewal)
admin.site.register(Notification)
