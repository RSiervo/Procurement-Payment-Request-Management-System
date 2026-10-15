from django.urls import path

from . import views

urlpatterns = [
    path("approvals/", views.PendingApprovalsView.as_view()),
    path("approvals/history/", views.ApprovalHistoryView.as_view()),
    path("approvals/bulk-approve/", views.BulkApproveView.as_view()),
]
