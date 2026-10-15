from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view()),
    path("reports/", views.ReportSummaryView.as_view()),
    path("reports/export/", views.ReportExportView.as_view()),
]
