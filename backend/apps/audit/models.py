from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel


class AuditLog(UUIDModel):
    """Append-only record of every significant action. Rows are never updated or deleted."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=40)
    # Only never-submitted drafts can be deleted; their entries keep the message text.
    request = models.ForeignKey(
        "requests.Request", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    message = models.CharField(max_length=300)
    previous_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    comments = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["request", "created_at"]), models.Index(fields=["action", "created_at"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Audit log entries are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit log entries cannot be deleted.")
