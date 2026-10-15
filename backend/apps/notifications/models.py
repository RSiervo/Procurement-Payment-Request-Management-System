from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class Event(models.TextChoices):
    REQUEST_SUBMITTED = "REQUEST_SUBMITTED", "Request Submitted"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED", "Approval Required"
    REQUEST_APPROVED = "REQUEST_APPROVED", "Request Approved"
    REQUEST_REJECTED = "REQUEST_REJECTED", "Request Rejected"
    REQUEST_RETURNED = "REQUEST_RETURNED", "Request Returned"
    CLARIFICATION_REQUESTED = "CLARIFICATION_REQUESTED", "Clarification Requested"
    OPS_ACTION_REQUIRED = "OPS_ACTION_REQUIRED", "Ready for OPS Processing"
    OPS_RECEIVED = "OPS_RECEIVED", "OPS Received"
    STATUS_UPDATED = "STATUS_UPDATED", "Processing Status Updated"
    REQUEST_COMPLETED = "REQUEST_COMPLETED", "Request Completed"
    COMMENT_ADDED = "COMMENT_ADDED", "New Comment"
    APPROVAL_REMINDER = "APPROVAL_REMINDER", "Approval Reminder"
    APPROVAL_ESCALATED = "APPROVAL_ESCALATED", "Approval Overdue (Escalation)"
    OPS_OVERDUE = "OPS_OVERDUE", "OPS Processing Overdue"
    PREPARED_FOR_YOU = "PREPARED_FOR_YOU", "Request Prepared for You"


class NotificationTemplate(UUIDModel, TimeStampedModel):
    """Administrator-editable wording. Placeholders use {{ name }} syntax."""

    event = models.CharField(max_length=30, choices=Event.choices, unique=True)
    subject = models.CharField(max_length=200)
    body = models.TextField()
    send_email = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["event"]

    def __str__(self):
        return self.get_event_display()


class EmailStatus(models.TextChoices):
    NOT_SENT = "NOT_SENT", "Not sent"
    PENDING = "PENDING", "Pending"
    SENT = "SENT", "Sent"
    FAILED = "FAILED", "Failed"


class Notification(UUIDModel):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    request = models.ForeignKey(
        "requests.Request", null=True, blank=True, on_delete=models.CASCADE, related_name="notifications"
    )
    event = models.CharField(max_length=30, choices=Event.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    email_status = models.CharField(max_length=10, choices=EmailStatus.choices, default=EmailStatus.NOT_SENT)
    email_error = models.CharField(max_length=255, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"])]
