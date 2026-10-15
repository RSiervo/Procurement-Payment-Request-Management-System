from django.urls import path

from . import views

urlpatterns = [
    path("audit-log/", views.AuditLogView.as_view()),
    path("audit-log/export/", views.AuditLogExportView.as_view()),
]
