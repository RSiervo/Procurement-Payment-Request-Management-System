from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDModel
from apps.workflows.models import ApproverType


class InstanceStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    RETURNED = "RETURNED", "Returned"
    CANCELLED = "CANCELLED", "Cancelled"


class ApprovalInstance(UUIDModel):
    """One pass of a request through a workflow. Each resubmission starts a new cycle."""

    request = models.ForeignKey("requests.Request", on_delete=models.CASCADE, related_name="approval_instances")
    workflow = models.ForeignKey("workflows.Workflow", null=True, on_delete=models.SET_NULL, related_name="+")
    workflow_name = models.CharField(max_length=120)
    requires_ops_processing = models.BooleanField(default=True)
    cycle = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=15, choices=InstanceStatus.choices, default=InstanceStatus.IN_PROGRESS)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["cycle"]
        constraints = [
            models.UniqueConstraint(fields=["request", "cycle"], name="approval_instance_cycle_unique"),
            models.UniqueConstraint(
                fields=["request"], condition=Q(status="IN_PROGRESS"), name="one_active_approval_per_request"
            ),
        ]


class StepStatus(models.TextChoices):
    WAITING = "WAITING", "Waiting"
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    RETURNED = "RETURNED", "Returned"
    SKIPPED = "SKIPPED", "Skipped"
    CANCELLED = "CANCELLED", "Cancelled"


class ApprovalStep(UUIDModel):
    """Snapshot of a workflow step, so later workflow edits never alter requests in flight."""

    instance = models.ForeignKey(ApprovalInstance, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=80)
    level_name = models.CharField(max_length=80, blank=True)
    approver_type = models.CharField(max_length=20, choices=ApproverType.choices)
    role = models.ForeignKey("users.Role", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    after_ops = models.BooleanField(default=False)

    status = models.CharField(max_length=10, choices=StepStatus.choices, default=StepStatus.WAITING)
    needs_clarification = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    acted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="approval_steps_acted"
    )
    acted_by_position = models.CharField(max_length=120, blank=True)
    acted_at = models.DateTimeField(null=True, blank=True)
    comments = models.TextField(blank=True)
    # Out-of-office cover: the approver this decision was made on behalf of.
    on_behalf_of = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    # Automations: when the approver was last reminded, and when the step was escalated.
    reminded_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    # The approver's e-signature as it was when they approved this step.
    signature = models.ImageField(upload_to="signatures/approvals/", blank=True)

    class Meta:
        ordering = ["order"]
        indexes = [models.Index(fields=["status", "approver_type"])]
        constraints = [models.UniqueConstraint(fields=["instance", "order"], name="approval_step_order_unique")]


class ActionType(models.TextChoices):
    APPROVE = "APPROVE", "Approved"
    REJECT = "REJECT", "Rejected"
    RETURN = "RETURN", "Returned for revision"
    CLARIFY = "CLARIFY", "Requested clarification"


class ApprovalAction(UUIDModel):
    """Immutable record of each decision. A step can carry several clarification requests."""

    step = models.ForeignKey(ApprovalStep, on_delete=models.CASCADE, related_name="actions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="approval_actions")
    actor_position = models.CharField(max_length=120, blank=True)
    action = models.CharField(max_length=10, choices=ActionType.choices)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["actor", "action", "created_at"])]
