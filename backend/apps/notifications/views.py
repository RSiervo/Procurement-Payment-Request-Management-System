from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import IsAdminRole
from apps.users.views import AuditedAdminMixin

from .models import Notification, NotificationTemplate
from .serializers import NotificationSerializer, NotificationTemplateSerializer


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The signed-in user's own notifications."""

    serializer_class = NotificationSerializer
    filterset_fields = ["is_read", "event"]
    search_fields = ["title", "message"]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).select_related("request")

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(is_read=False).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        note = self.get_object()
        if not note.is_read:
            note.is_read, note.read_at = True, timezone.now()
            note.save(update_fields=["is_read", "read_at"])
        return Response(NotificationSerializer(note).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationTemplateViewSet(AuditedAdminMixin, mixins.ListModelMixin, mixins.UpdateModelMixin,
                                  viewsets.GenericViewSet):
    queryset = NotificationTemplate.objects.all()
    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsAdminRole]
    pagination_class = None
    http_method_names = ["get", "patch", "head", "options"]
    audit_label = "notification template"
