from django.db.models import F
from rest_framework import viewsets

from apps.core.permissions import IsAdminRole
from apps.users.views import AuditedAdminMixin

from .models import Workflow
from .serializers import WorkflowSerializer


class WorkflowViewSet(AuditedAdminMixin, viewsets.ModelViewSet):
    """Approval routes. Editing one never affects requests already in approval."""

    queryset = (
        Workflow.objects.select_related("request_type", "department")
        .prefetch_related("steps__role", "steps__user", "steps__level")
        .order_by("request_type__sort_order", F("min_amount").asc(nulls_first=True), "name")
    )
    serializer_class = WorkflowSerializer
    permission_classes = [IsAdminRole]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filterset_fields = ["request_type__code", "is_active"]
    audit_label = "workflow"

    def perform_create(self, serializer):
        self._audit("CREATED", serializer.save(created_by=self.request.user, updated_by=self.request.user))

    def perform_update(self, serializer):
        self._audit("UPDATED", serializer.save(updated_by=self.request.user))
